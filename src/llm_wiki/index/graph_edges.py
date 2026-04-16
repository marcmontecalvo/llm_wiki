"""Graph edge index for fast relationship queries."""

import hashlib
import json
import logging
from collections import deque
from pathlib import Path
from typing import Any

from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


def _edge_id(source: str, target: str, edge_type: str) -> str:
    """Generate a stable edge ID from source, target, and type."""
    key = f"{source}::{target}::{edge_type}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


class GraphEdgeIndex:
    """Index for tracking typed, weighted graph edges between wiki nodes.

    Nodes are identified by page ID (or entity name for semantic edges).
    Edges come from three sources:
      - ``links``: [[page-id]] wiki-link syntax extracted from page bodies.
      - Relationship extraction results stored in page frontmatter under the
        ``relationships`` key (types like ``uses``, ``depends_on``, etc.).
      - Explicit frontmatter fields (future: ``related``, ``part_of``, …).

    The on-disk format is ``wiki_system/index/edges.json``::

        {
          "edges": {
            "<edge-id>": {
              "source": "...", "target": "...", "type": "...",
              "weight": 0.9, "bidirectional": false, "metadata": {}
            }
          },
          "by_source": {"<node>": ["<edge-id>", ...]},
          "by_target": {"<node>": ["<edge-id>", ...]},
          "by_type":   {"<type>": ["<edge-id>", ...]}
        }
    """

    def __init__(self, index_dir: Path | None = None):
        """Initialise graph edge index.

        Args:
            index_dir: Directory for storing the index file.
                       Defaults to ``wiki_system/index``.
        """
        self.index_dir = index_dir or Path("wiki_system/index")
        self.index_dir.mkdir(parents=True, exist_ok=True)

        # edge_id -> edge dict
        self.edges: dict[str, dict[str, Any]] = {}
        # node -> list[edge_id]
        self.by_source: dict[str, list[str]] = {}
        self.by_target: dict[str, list[str]] = {}
        # edge_type -> list[edge_id]
        self.by_type: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def _add_to_lookup(self, lookup: dict[str, list[str]], key: str, eid: str) -> None:
        if key not in lookup:
            lookup[key] = []
        if eid not in lookup[key]:
            lookup[key].append(eid)

    def _remove_from_lookup(self, lookup: dict[str, list[str]], key: str, eid: str) -> None:
        if key in lookup:
            try:
                lookup[key].remove(eid)
            except ValueError:
                pass
            if not lookup[key]:
                del lookup[key]

    def _register_edge(self, eid: str, edge: dict[str, Any]) -> None:
        self.edges[eid] = edge
        self._add_to_lookup(self.by_source, edge["source"], eid)
        self._add_to_lookup(self.by_target, edge["target"], eid)
        self._add_to_lookup(self.by_type, edge["type"], eid)

    def _unregister_edge(self, eid: str) -> None:
        edge = self.edges.pop(eid, None)
        if edge is None:
            return
        self._remove_from_lookup(self.by_source, edge["source"], eid)
        self._remove_from_lookup(self.by_target, edge["target"], eid)
        self._remove_from_lookup(self.by_type, edge["type"], eid)

    # ------------------------------------------------------------------
    # Public API: adding / removing edges
    # ------------------------------------------------------------------

    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: str,
        weight: float = 1.0,
        bidirectional: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add or update an edge in the index.

        If an edge with the same (source, target, edge_type) already exists,
        it is overwritten with the new weight and metadata.

        Args:
            source: Source node ID.
            target: Target node ID.
            edge_type: Relationship type (e.g. ``"uses"``, ``"links"``).
            weight: Importance score 0.0–1.0.
            bidirectional: If True, also registers the reverse edge.
            metadata: Additional edge properties (description, page_id, …).

        Returns:
            The edge ID.
        """
        weight = max(0.0, min(1.0, float(weight)))
        eid = _edge_id(source, target, edge_type)
        edge: dict[str, Any] = {
            "source": source,
            "target": target,
            "type": edge_type,
            "weight": weight,
            "bidirectional": bidirectional,
            "metadata": metadata or {},
        }
        # If overwriting a previously bidirectional edge that is now not
        # bidirectional (or simply re-registering), clean up the stale reverse.
        old_edge = self.edges.get(eid)
        if old_edge and old_edge.get("bidirectional") and not bidirectional:
            old_rev_eid = _edge_id(target, source, edge_type)
            self._unregister_edge(old_rev_eid)

        self._register_edge(eid, edge)

        if bidirectional:
            rev_eid = _edge_id(target, source, edge_type)
            rev_edge: dict[str, Any] = {
                "source": target,
                "target": source,
                "type": edge_type,
                "weight": weight,
                "bidirectional": True,
                "metadata": metadata or {},
            }
            self._register_edge(rev_eid, rev_edge)

        return eid

    def remove_edges_for_page(self, page_id: str) -> int:
        """Remove all edges where *page_id* is the source.

        Args:
            page_id: Node identifier whose outgoing edges should be removed.

        Returns:
            Number of edges removed.
        """
        eids = list(self.by_source.get(page_id, []))
        for eid in eids:
            self._unregister_edge(eid)
        return len(eids)

    def update_page_links(self, page_id: str, linked_targets: list[str]) -> int:
        """Replace all ``links``-type edges for *page_id* with a new set.

        Args:
            page_id: Source node (the page doing the linking).
            linked_targets: Target node IDs extracted from [[wikilinks]].

        Returns:
            Number of link edges now registered for this page.
        """
        # Remove existing link edges from this source
        for eid in list(self.by_source.get(page_id, [])):
            if self.edges[eid]["type"] == "links":
                self._unregister_edge(eid)

        for target in set(linked_targets):
            self.add_edge(page_id, target, "links", weight=1.0, bidirectional=False)

        return len(set(linked_targets))

    def update_page_relationships(self, page_id: str, relationships: list[dict[str, Any]]) -> int:
        """Replace all semantic relationship edges for *page_id*.

        Relationships come from the extraction pipeline and are stored in
        page frontmatter under the ``relationships`` key.

        Args:
            page_id: Source page ID (used as fallback when source_entity is
                     the page title rather than an ID).
            relationships: List of relationship dicts with keys:
                ``source_entity``, ``relationship_type``, ``target_entity``,
                ``confidence``, ``bidirectional``, ``description`` (opt.).

        Returns:
            Number of relationship edges registered.
        """
        # Remove existing non-link edges that belong to this page.
        # This covers two cases:
        #   1. Edges where source == page_id (most common).
        #   2. Edges where source_entity != page_id but metadata["page_id"] == page_id
        #      (entity-sourced semantic edges from a prior extraction pass).
        eids_to_remove = []
        for eid, edge in list(self.edges.items()):
            if edge["type"] == "links":
                continue
            if edge["source"] == page_id or edge.get("metadata", {}).get("page_id") == page_id:
                eids_to_remove.append(eid)
        for eid in eids_to_remove:
            self._unregister_edge(eid)

        count = 0
        for rel in relationships:
            source = str(rel.get("source_entity", page_id)).strip() or page_id
            target = str(rel.get("target_entity", "")).strip()
            rel_type = str(rel.get("relationship_type", "related_to")).strip().lower()
            confidence = float(rel.get("confidence", 0.9))
            bidir = bool(rel.get("bidirectional", False))
            description = rel.get("description", "")

            if not target:
                continue

            self.add_edge(
                source,
                target,
                rel_type,
                weight=confidence,
                bidirectional=bidir,
                metadata={"page_id": page_id, "description": description or ""},
            )
            count += 1

        return count

    # ------------------------------------------------------------------
    # Query interface
    # ------------------------------------------------------------------

    def find_outgoing(self, node: str, edge_type: str | None = None) -> list[dict[str, Any]]:
        """Return all edges going *out* from *node*.

        Args:
            node: Source node ID.
            edge_type: If given, filter to this edge type only.

        Returns:
            List of edge dicts.
        """
        eids = self.by_source.get(node, [])
        result = [self.edges[eid] for eid in eids if eid in self.edges]
        if edge_type:
            result = [e for e in result if e["type"] == edge_type]
        return result

    def find_incoming(self, node: str, edge_type: str | None = None) -> list[dict[str, Any]]:
        """Return all edges coming *into* *node*.

        Args:
            node: Target node ID.
            edge_type: If given, filter to this edge type only.

        Returns:
            List of edge dicts.
        """
        eids = self.by_target.get(node, [])
        result = [self.edges[eid] for eid in eids if eid in self.edges]
        if edge_type:
            result = [e for e in result if e["type"] == edge_type]
        return result

    def find_neighbors(self, node: str, depth: int = 1) -> set[str]:
        """Return all nodes reachable from *node* within *depth* hops.

        Traverses both outgoing and incoming edges (undirected neighbourhood).

        Args:
            node: Starting node ID.
            depth: Maximum number of hops.

        Returns:
            Set of neighbour node IDs (does not include *node* itself).
        """
        if depth < 1:
            return set()

        visited: set[str] = {node}
        frontier: deque[tuple[str, int]] = deque([(node, 0)])
        neighbours: set[str] = set()

        while frontier:
            current, current_depth = frontier.popleft()
            if current_depth >= depth:
                continue

            adjacent: set[str] = set()
            for edge in self.find_outgoing(current):
                adjacent.add(edge["target"])
            for edge in self.find_incoming(current):
                adjacent.add(edge["source"])

            for adj in adjacent:
                if adj not in visited:
                    visited.add(adj)
                    neighbours.add(adj)
                    frontier.append((adj, current_depth + 1))

        return neighbours

    def find_path(self, source: str, target: str, max_depth: int = 3) -> list[list[dict[str, Any]]]:
        """Find directed paths from *source* to *target*.

        Uses BFS; only follows outgoing edges. Returns all shortest paths up
        to *max_depth* hops.

        Args:
            source: Starting node ID.
            target: Destination node ID.
            max_depth: Maximum path length (number of edges).

        Returns:
            List of paths; each path is a list of edge dicts.
        """
        if source == target:
            return [[]]

        # BFS: state = (current_node, path_so_far)
        queue: deque[tuple[str, list[dict[str, Any]]]] = deque([(source, [])])
        found_paths: list[list[dict[str, Any]]] = []
        visited_at_depth: dict[str, int] = {source: 0}

        while queue:
            current, path = queue.popleft()

            if len(path) >= max_depth:
                continue

            for edge in self.find_outgoing(current):
                next_node = edge["target"]
                new_path = path + [edge]

                if next_node == target:
                    found_paths.append(new_path)
                    continue

                # Allow revisiting a node at the same or shallower depth so
                # that all shortest paths are discovered (not just the first).
                prev_depth = visited_at_depth.get(next_node, max_depth + 1)
                if len(new_path) <= prev_depth:
                    visited_at_depth[next_node] = len(new_path)
                    queue.append((next_node, new_path))

        return found_paths

    def get_subgraph(self, nodes: set[str]) -> dict[str, Any]:
        """Extract the subgraph induced by *nodes*.

        Args:
            nodes: Set of node IDs to include.

        Returns:
            Dict with ``"nodes"`` (list) and ``"edges"`` (list of edge dicts)
            where both endpoints are in *nodes*.
        """
        sub_edges = [
            edge
            for edge in self.edges.values()
            if edge["source"] in nodes and edge["target"] in nodes
        ]
        return {"nodes": sorted(nodes), "edges": sub_edges}

    def get_stats(self) -> dict[str, Any]:
        """Return index statistics.

        Returns:
            Dict with total_edges, total_nodes, edges_by_type.
        """
        all_nodes = set(self.by_source) | set(self.by_target)
        edges_by_type = {etype: len(eids) for etype, eids in self.by_type.items()}
        return {
            "total_edges": len(self.edges),
            "total_nodes": len(all_nodes),
            "edges_by_type": edges_by_type,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Persist index to ``wiki_system/index/edges.json``."""
        index_file = self.index_dir / "edges.json"
        data = {
            "edges": self.edges,
            "by_source": self.by_source,
            "by_target": self.by_target,
            "by_type": self.by_type,
        }
        with index_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        logger.info(f"Saved graph edge index ({len(self.edges)} edges)")

    def load(self) -> None:
        """Load index from ``wiki_system/index/edges.json``."""
        index_file = self.index_dir / "edges.json"
        if not index_file.exists():
            logger.info("No existing graph edge index found")
            return

        with index_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        self.edges = data.get("edges", {})
        self.by_source = data.get("by_source", {})
        self.by_target = data.get("by_target", {})
        self.by_type = data.get("by_type", {})
        logger.info(f"Loaded graph edge index ({len(self.edges)} edges)")

    def rebuild_from_pages(self, wiki_base: Path | None = None) -> int:
        """Rebuild index by scanning all enriched wiki pages.

        Reads ``relationships`` and wiki-link references from each page's
        frontmatter and body content.

        Args:
            wiki_base: Base wiki directory (defaults to ``wiki_system/``).

        Returns:
            Number of pages scanned.
        """
        wiki_base = wiki_base or Path("wiki_system")
        self.edges.clear()
        self.by_source.clear()
        self.by_target.clear()
        self.by_type.clear()

        domains_dir = wiki_base / "domains"
        if not domains_dir.exists():
            logger.warning(f"Domains directory not found: {domains_dir}")
            return 0

        import re

        count = 0
        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue
            pages_dir = domain_dir / "pages"
            if not pages_dir.exists():
                continue

            for page_file in pages_dir.glob("*.md"):
                try:
                    content = page_file.read_text(encoding="utf-8")
                    metadata, body = parse_frontmatter(content)
                    page_id = metadata.get("id", page_file.stem)

                    # Wiki-link edges
                    links = re.findall(r"\[\[([^\]]+)\]\]", body)
                    self.update_page_links(page_id, links)

                    # Relationship edges from frontmatter
                    rels = metadata.get("relationships", [])
                    if isinstance(rels, list) and rels:
                        self.update_page_relationships(page_id, rels)

                    count += 1
                except Exception as e:
                    logger.error(f"Failed to index {page_file}: {e}")

        logger.info(f"Rebuilt graph edge index: {count} pages, {len(self.edges)} edges")
        return count
