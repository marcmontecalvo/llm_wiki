"""Tests for GraphEdgeIndex (Issue #79)."""

from pathlib import Path

import pytest

from llm_wiki.index.graph_edges import GraphEdgeIndex, _edge_id


class TestEdgeId:
    """Tests for the edge ID helper."""

    def test_stable(self):
        assert _edge_id("a", "b", "uses") == _edge_id("a", "b", "uses")

    def test_distinct_for_different_inputs(self):
        assert _edge_id("a", "b", "uses") != _edge_id("b", "a", "uses")
        assert _edge_id("a", "b", "uses") != _edge_id("a", "b", "links")
        assert _edge_id("a", "b", "uses") != _edge_id("a", "c", "uses")


class TestGraphEdgeIndex:
    """Tests for GraphEdgeIndex."""

    @pytest.fixture
    def index(self, temp_dir: Path) -> GraphEdgeIndex:
        return GraphEdgeIndex(index_dir=temp_dir / "index")

    # ------------------------------------------------------------------
    # add_edge
    # ------------------------------------------------------------------

    def test_add_edge_registers_lookups(self, index: GraphEdgeIndex):
        eid = index.add_edge("python", "pip", "uses", weight=0.9)
        assert eid in index.edges
        assert eid in index.by_source["python"]
        assert eid in index.by_target["pip"]
        assert eid in index.by_type["uses"]

    def test_add_edge_clamps_weight(self, index: GraphEdgeIndex):
        eid = index.add_edge("a", "b", "uses", weight=5.0)
        assert index.edges[eid]["weight"] == 1.0

        eid2 = index.add_edge("a", "c", "uses", weight=-1.0)
        assert index.edges[eid2]["weight"] == 0.0

    def test_add_edge_bidirectional_creates_reverse(self, index: GraphEdgeIndex):
        index.add_edge("a", "b", "related_to", bidirectional=True)
        # Forward
        assert any(e["source"] == "a" and e["target"] == "b" for e in index.edges.values())
        # Reverse
        assert any(e["source"] == "b" and e["target"] == "a" for e in index.edges.values())

    def test_add_edge_overwrites_existing(self, index: GraphEdgeIndex):
        index.add_edge("a", "b", "uses", weight=0.5)
        index.add_edge("a", "b", "uses", weight=0.8, metadata={"page_id": "x"})
        eid = _edge_id("a", "b", "uses")
        assert index.edges[eid]["weight"] == 0.8
        assert index.edges[eid]["metadata"]["page_id"] == "x"
        # Should not duplicate in lookup lists
        assert index.by_source["a"].count(eid) == 1

    def test_add_edge_bidirectional_overwrite_cleans_reverse(self, index: GraphEdgeIndex):
        """Regression: overwriting a bidirectional edge as non-bidirectional must remove
        the orphaned reverse edge (HIGH bug from adversarial review)."""
        index.add_edge("a", "b", "uses", bidirectional=True)
        # Overwrite as unidirectional
        index.add_edge("a", "b", "uses", bidirectional=False)
        # Reverse edge b->a must be gone
        assert not index.find_outgoing("b", "uses")
        rev_eid = _edge_id("b", "a", "uses")
        assert rev_eid not in index.edges

    # ------------------------------------------------------------------
    # remove_edges_for_page
    # ------------------------------------------------------------------

    def test_remove_edges_for_page(self, index: GraphEdgeIndex):
        index.add_edge("page1", "target1", "links")
        index.add_edge("page1", "target2", "links")
        index.add_edge("page2", "target1", "links")

        removed = index.remove_edges_for_page("page1")

        assert removed == 2
        assert "page1" not in index.by_source
        assert "page2" in index.by_source  # unaffected

    def test_remove_edges_nonexistent_page(self, index: GraphEdgeIndex):
        assert index.remove_edges_for_page("ghost") == 0

    # ------------------------------------------------------------------
    # update_page_links
    # ------------------------------------------------------------------

    def test_update_page_links_adds_link_edges(self, index: GraphEdgeIndex):
        index.update_page_links("page1", ["page2", "page3"])
        out = index.find_outgoing("page1", "links")
        targets = {e["target"] for e in out}
        assert targets == {"page2", "page3"}

    def test_update_page_links_replaces_existing(self, index: GraphEdgeIndex):
        index.update_page_links("page1", ["old"])
        index.update_page_links("page1", ["new1", "new2"])
        targets = {e["target"] for e in index.find_outgoing("page1", "links")}
        assert targets == {"new1", "new2"}
        assert "old" not in targets

    def test_update_page_links_deduplicates(self, index: GraphEdgeIndex):
        count = index.update_page_links("page1", ["dup", "dup", "dup"])
        assert count == 1

    def test_update_page_links_does_not_remove_semantic_edges(self, index: GraphEdgeIndex):
        index.add_edge("page1", "python", "uses")
        index.update_page_links("page1", ["page2"])
        # Semantic edge must survive
        sem = index.find_outgoing("page1", "uses")
        assert len(sem) == 1

    # ------------------------------------------------------------------
    # update_page_relationships
    # ------------------------------------------------------------------

    def test_update_page_relationships(self, index: GraphEdgeIndex):
        rels = [
            {
                "source_entity": "Python",
                "relationship_type": "uses",
                "target_entity": "pip",
                "confidence": 0.95,
                "bidirectional": False,
            },
        ]
        count = index.update_page_relationships("python-page", rels)
        assert count == 1
        edges = index.find_outgoing("Python", "uses")
        assert any(e["target"] == "pip" for e in edges)

    def test_update_page_relationships_skips_empty_target(self, index: GraphEdgeIndex):
        rels = [{"source_entity": "A", "relationship_type": "uses", "target_entity": ""}]
        count = index.update_page_relationships("a-page", rels)
        assert count == 0

    def test_update_page_relationships_replaces_existing(self, index: GraphEdgeIndex):
        rels1 = [
            {
                "source_entity": "page1",
                "relationship_type": "uses",
                "target_entity": "old",
                "confidence": 0.8,
                "bidirectional": False,
            }
        ]
        index.update_page_relationships("page1", rels1)

        rels2 = [
            {
                "source_entity": "page1",
                "relationship_type": "depends_on",
                "target_entity": "new",
                "confidence": 0.9,
                "bidirectional": False,
            }
        ]
        index.update_page_relationships("page1", rels2)

        # Old semantic edges gone
        assert not index.find_outgoing("page1", "uses")
        # New edge present
        assert index.find_outgoing("page1", "depends_on")

    def test_update_page_relationships_does_not_remove_link_edges(self, index: GraphEdgeIndex):
        index.update_page_links("page1", ["linked"])
        rels = [
            {
                "source_entity": "page1",
                "relationship_type": "uses",
                "target_entity": "tool",
                "confidence": 0.9,
                "bidirectional": False,
            }
        ]
        index.update_page_relationships("page1", rels)
        # Link edges must survive
        assert index.find_outgoing("page1", "links")

    def test_update_page_relationships_removes_zombie_edges_on_reprocess(
        self, index: GraphEdgeIndex
    ):
        """Regression: when source_entity != page_id, re-processing the page must
        remove old entity-sourced edges (HIGH zombie-edge bug from adversarial review)."""
        rels1 = [
            {
                "source_entity": "Python",
                "relationship_type": "uses",
                "target_entity": "pip",
                "confidence": 0.9,
                "bidirectional": False,
            }
        ]
        index.update_page_relationships("python-page", rels1)

        # Sanity: edge was created from entity "Python", not from "python-page"
        assert index.find_outgoing("Python", "uses")

        # Re-process with completely different relationships
        rels2 = [
            {
                "source_entity": "Python",
                "relationship_type": "depends_on",
                "target_entity": "cpython",
                "confidence": 0.95,
                "bidirectional": False,
            }
        ]
        index.update_page_relationships("python-page", rels2)

        # Old edge must be gone, not zombied
        assert not index.find_outgoing("Python", "uses")
        assert index.find_outgoing("Python", "depends_on")

    # ------------------------------------------------------------------
    # find_outgoing / find_incoming
    # ------------------------------------------------------------------

    def test_find_outgoing(self, index: GraphEdgeIndex):
        index.add_edge("a", "b", "uses")
        index.add_edge("a", "c", "links")
        index.add_edge("d", "b", "uses")

        out_all = index.find_outgoing("a")
        assert len(out_all) == 2

        out_uses = index.find_outgoing("a", "uses")
        assert len(out_uses) == 1
        assert out_uses[0]["target"] == "b"

    def test_find_outgoing_no_results(self, index: GraphEdgeIndex):
        assert index.find_outgoing("ghost") == []

    def test_find_incoming(self, index: GraphEdgeIndex):
        index.add_edge("a", "b", "uses")
        index.add_edge("c", "b", "links")

        inc = index.find_incoming("b")
        assert len(inc) == 2

        inc_uses = index.find_incoming("b", "uses")
        assert len(inc_uses) == 1
        assert inc_uses[0]["source"] == "a"

    # ------------------------------------------------------------------
    # find_neighbors
    # ------------------------------------------------------------------

    def test_find_neighbors_depth_1(self, index: GraphEdgeIndex):
        index.add_edge("a", "b", "uses")
        index.add_edge("b", "c", "uses")

        nbrs = index.find_neighbors("a", depth=1)
        assert nbrs == {"b"}

    def test_find_neighbors_depth_2(self, index: GraphEdgeIndex):
        index.add_edge("a", "b", "uses")
        index.add_edge("b", "c", "uses")

        nbrs = index.find_neighbors("a", depth=2)
        assert {"b", "c"}.issubset(nbrs)

    def test_find_neighbors_includes_incoming_nodes(self, index: GraphEdgeIndex):
        index.add_edge("x", "a", "uses")
        nbrs = index.find_neighbors("a", depth=1)
        assert "x" in nbrs

    def test_find_neighbors_depth_0(self, index: GraphEdgeIndex):
        index.add_edge("a", "b", "uses")
        assert index.find_neighbors("a", depth=0) == set()

    def test_find_neighbors_unknown_node(self, index: GraphEdgeIndex):
        assert index.find_neighbors("ghost") == set()

    # ------------------------------------------------------------------
    # find_path
    # ------------------------------------------------------------------

    def test_find_path_direct(self, index: GraphEdgeIndex):
        index.add_edge("a", "b", "uses")
        paths = index.find_path("a", "b")
        assert len(paths) == 1
        assert paths[0][0]["source"] == "a"
        assert paths[0][0]["target"] == "b"

    def test_find_path_two_hops(self, index: GraphEdgeIndex):
        index.add_edge("a", "b", "uses")
        index.add_edge("b", "c", "uses")
        paths = index.find_path("a", "c")
        assert any(len(p) == 2 for p in paths)

    def test_find_path_no_path(self, index: GraphEdgeIndex):
        index.add_edge("a", "b", "uses")
        paths = index.find_path("b", "a")  # directed, no reverse
        assert paths == []

    def test_find_path_same_node(self, index: GraphEdgeIndex):
        paths = index.find_path("a", "a")
        assert paths == [[]]

    def test_find_path_respects_max_depth(self, index: GraphEdgeIndex):
        index.add_edge("a", "b", "uses")
        index.add_edge("b", "c", "uses")
        index.add_edge("c", "d", "uses")
        paths = index.find_path("a", "d", max_depth=2)
        assert paths == []  # requires 3 hops

    def test_find_path_all_equal_length_paths(self, index: GraphEdgeIndex):
        """Regression: all equal-length paths through different intermediate nodes
        must be returned (previously missed due to visited_at_depth < vs <= bug)."""
        # Two paths of equal length to target: a->b->d->t and a->c->d->t
        index.add_edge("a", "b", "uses")
        index.add_edge("a", "c", "uses")
        index.add_edge("b", "d", "uses")
        index.add_edge("c", "d", "uses")
        index.add_edge("d", "t", "uses")

        paths = index.find_path("a", "t", max_depth=4)
        # Both length-3 paths must be found
        assert len(paths) == 2
        path_nodes = [tuple(e["source"] for e in p) + (p[-1]["target"],) for p in paths]
        assert ("a", "b", "d", "t") in path_nodes
        assert ("a", "c", "d", "t") in path_nodes

    # ------------------------------------------------------------------
    # get_subgraph
    # ------------------------------------------------------------------

    def test_get_subgraph_includes_internal_edges(self, index: GraphEdgeIndex):
        index.add_edge("a", "b", "uses")
        index.add_edge("b", "c", "uses")
        index.add_edge("a", "d", "uses")  # d not in subgraph

        sub = index.get_subgraph({"a", "b", "c"})
        assert "d" not in sub["nodes"]
        # a->b and b->c should be included; a->d should not
        edge_pairs = {(e["source"], e["target"]) for e in sub["edges"]}
        assert ("a", "b") in edge_pairs
        assert ("b", "c") in edge_pairs
        assert ("a", "d") not in edge_pairs

    def test_get_subgraph_empty_nodes(self, index: GraphEdgeIndex):
        sub = index.get_subgraph(set())
        assert sub["nodes"] == []
        assert sub["edges"] == []

    # ------------------------------------------------------------------
    # get_stats
    # ------------------------------------------------------------------

    def test_get_stats(self, index: GraphEdgeIndex):
        index.add_edge("a", "b", "uses")
        index.add_edge("b", "c", "links")
        stats = index.get_stats()
        assert stats["total_edges"] == 2
        assert stats["total_nodes"] == 3
        assert stats["edges_by_type"]["uses"] == 1
        assert stats["edges_by_type"]["links"] == 1

    # ------------------------------------------------------------------
    # save / load
    # ------------------------------------------------------------------

    def test_save_and_load_roundtrip(self, index: GraphEdgeIndex, temp_dir: Path):
        index.add_edge("a", "b", "uses", weight=0.8, metadata={"page_id": "p1"})
        index.add_edge("b", "c", "links", bidirectional=True)
        index.save()

        index2 = GraphEdgeIndex(index_dir=temp_dir / "index")
        index2.load()

        assert len(index2.edges) == len(index.edges)
        assert "a" in index2.by_source
        assert "b" in index2.by_target
        assert "uses" in index2.by_type

    def test_load_nonexistent_is_noop(self, index: GraphEdgeIndex):
        index.load()  # no file on disk
        assert index.edges == {}

    # ------------------------------------------------------------------
    # rebuild_from_pages
    # ------------------------------------------------------------------

    def test_rebuild_from_pages(self, index: GraphEdgeIndex, temp_dir: Path):
        wiki_base = temp_dir / "wiki"
        pages_dir = wiki_base / "domains" / "general" / "pages"
        pages_dir.mkdir(parents=True)

        (pages_dir / "page1.md").write_text(
            "---\nid: page1\ntitle: Page One\n---\nLinks to [[page2]].\n"
        )
        (pages_dir / "page2.md").write_text(
            "---\nid: page2\ntitle: Page Two\nrelationships:\n"
            "  - source_entity: page2\n    relationship_type: uses\n"
            "    target_entity: tool\n    confidence: 0.9\n    bidirectional: false\n---\n\n"
        )

        count = index.rebuild_from_pages(wiki_base)

        assert count == 2
        # Wiki-link edge
        assert any(e["target"] == "page2" for e in index.find_outgoing("page1", "links"))
        # Relationship edge
        assert any(e["target"] == "tool" for e in index.find_outgoing("page2", "uses"))

    def test_rebuild_clears_existing_data(self, index: GraphEdgeIndex, temp_dir: Path):
        index.add_edge("stale", "data", "uses")
        wiki_base = temp_dir / "wiki"
        pages_dir = wiki_base / "domains" / "d" / "pages"
        pages_dir.mkdir(parents=True)
        (pages_dir / "fresh.md").write_text("---\nid: fresh\ntitle: Fresh\n---\nContent\n")

        index.rebuild_from_pages(wiki_base)

        assert "stale" not in index.by_source

    def test_rebuild_handles_missing_domains(self, index: GraphEdgeIndex, temp_dir: Path):
        count = index.rebuild_from_pages(temp_dir / "nonexistent_wiki")
        assert count == 0
