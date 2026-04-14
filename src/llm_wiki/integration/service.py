"""Deterministic integration service for merging extracted metadata."""

import copy
import logging
from datetime import datetime
from typing import Any

from llm_wiki.models.integration import (
    Change,
    IntegrationConflict,
    IntegrationResult,
    IntegrationState,
    MergeStrategies,
    MergeStrategy,
)

logger = logging.getLogger(__name__)


class IntegrationError(Exception):
    """Raised when integration fails."""

    pass


class DeterministicIntegrator:
    """Handles deterministic integration of extracted metadata into existing pages."""

    # Confidence threshold for determining if a value is "newer" or "better"
    CONFIDENCE_THRESHOLD = 0.1

    def __init__(self, strategies: MergeStrategies | None = None):
        """Initialize integrator with merge strategies.

        Args:
            strategies: Merge strategy configuration. Uses defaults if None.
        """
        self.strategies = strategies or MergeStrategies()
        self.history: dict[str, list[IntegrationState]] = {}

    def integrate(
        self,
        page_id: str,
        existing_page: dict[str, Any],
        extracted_data: dict[str, Any],
        auto_resolve_conflicts: bool = False,
    ) -> IntegrationResult:
        """Integrate extracted data into existing page.

        Args:
            page_id: Unique page identifier
            existing_page: Existing page data
            extracted_data: Extracted metadata
            auto_resolve_conflicts: If True, automatically resolve conflicts using strategies

        Returns:
            IntegrationResult with changes, conflicts, and status

        Raises:
            IntegrationError: If integration fails
        """
        result = IntegrationResult(page_id=page_id)

        try:
            # Create snapshot for rollback support
            snapshot = copy.deepcopy(existing_page)
            state = IntegrationState(page_id=page_id, snapshot=snapshot, timestamp=datetime.now())

            # Initialize tracking
            result.total_fields_checked = 0

            # Detect and apply changes for each field
            self._integrate_field(
                result,
                existing_page,
                extracted_data,
                "title",
                self.strategies.title,
                auto_resolve_conflicts,
            )
            self._integrate_field(
                result,
                existing_page,
                extracted_data,
                "domain",
                self.strategies.domain,
                auto_resolve_conflicts,
            )
            self._integrate_field(
                result,
                existing_page,
                extracted_data,
                "tags",
                self.strategies.tags,
                auto_resolve_conflicts,
            )
            self._integrate_field(
                result,
                existing_page,
                extracted_data,
                "summary",
                self.strategies.summary,
                auto_resolve_conflicts,
            )
            self._integrate_field(
                result,
                existing_page,
                extracted_data,
                "entities",
                self.strategies.entities,
                auto_resolve_conflicts,
            )
            self._integrate_field(
                result,
                existing_page,
                extracted_data,
                "concepts",
                self.strategies.concepts,
                auto_resolve_conflicts,
            )
            self._integrate_field(
                result,
                existing_page,
                extracted_data,
                "claims",
                self.strategies.claims,
                auto_resolve_conflicts,
            )
            self._integrate_field(
                result,
                existing_page,
                extracted_data,
                "relationships",
                self.strategies.relationships,
                auto_resolve_conflicts,
            )
            self._integrate_field(
                result,
                existing_page,
                extracted_data,
                "links",
                self.strategies.links,
                auto_resolve_conflicts,
            )
            self._integrate_field(
                result,
                existing_page,
                extracted_data,
                "sources",
                self.strategies.sources,
                auto_resolve_conflicts,
            )
            self._integrate_field(
                result,
                existing_page,
                extracted_data,
                "confidence",
                self.strategies.confidence,
                auto_resolve_conflicts,
            )

            # Handle updated timestamp
            if result.has_changes():
                existing_page["updated_at"] = datetime.now()
                result.changes.append(
                    Change(
                        field="updated_at",
                        old_value=snapshot.get("updated_at"),
                        new_value=existing_page["updated_at"],
                        change_type="updated",
                        timestamp=datetime.now(),
                        reason="Integration applied",
                    )
                )

            # Store history for rollback support
            state.result = result
            if page_id not in self.history:
                self.history[page_id] = []
            self.history[page_id].append(state)

            result.success = True
            result.timestamp = datetime.now()

            logger.info(
                f"Integration complete for page {page_id}: "
                f"{result.fields_changed} changes, "
                f"{result.conflicts_detected} conflicts"
            )

            return result

        except Exception as e:
            result.success = False
            result.error = str(e)
            logger.error(f"Integration failed for page {page_id}: {e}")
            raise IntegrationError(f"Integration failed for page {page_id}: {e}") from e

    def _integrate_field(
        self,
        result: IntegrationResult,
        existing_page: dict[str, Any],
        extracted_data: dict[str, Any],
        field_name: str,
        strategy: MergeStrategy,
        auto_resolve: bool,
    ) -> None:
        """Integrate a single field using specified strategy.

        Args:
            result: Integration result to update
            existing_page: Existing page data (modified in-place)
            extracted_data: Extracted metadata
            field_name: Field to integrate
            strategy: Merge strategy to use
            auto_resolve: Whether to automatically resolve conflicts
        """
        result.total_fields_checked += 1

        existing_value = existing_page.get(field_name)
        extracted_value = extracted_data.get(field_name)

        # No extracted value - nothing to do
        if extracted_value is None:
            return

        # No existing value - add extracted
        if existing_value is None:
            existing_page[field_name] = extracted_value
            result.changes.append(
                Change(
                    field=field_name,
                    old_value=None,
                    new_value=extracted_value,
                    change_type="added",
                    timestamp=datetime.now(),
                    reason=f"Added extracted value using {strategy} strategy",
                )
            )
            result.fields_changed += 1
            return

        # Apply merge strategy
        if strategy == "keep_existing":
            # No change - keep existing value
            pass
        elif strategy == "use_extracted":
            # Replace with extracted value
            if existing_value != extracted_value:
                existing_page[field_name] = extracted_value
                result.changes.append(
                    Change(
                        field=field_name,
                        old_value=existing_value,
                        new_value=extracted_value,
                        change_type="updated",
                        timestamp=datetime.now(),
                        reason=f"Replaced with extracted value using {strategy} strategy",
                    )
                )
                result.fields_changed += 1
        elif strategy == "union":
            # Merge as union for list-based fields
            self._merge_union(
                result, existing_page, extracted_data, field_name, existing_value, extracted_value
            )
        elif strategy == "deduplicate_merge":
            # Merge with deduplication
            self._merge_deduplicate(
                result, existing_page, extracted_data, field_name, existing_value, extracted_value
            )
        elif strategy == "prefer_newer":
            # Merge preferring newer/higher confidence values
            self._merge_prefer_newer(
                result,
                existing_page,
                extracted_data,
                field_name,
                existing_value,
                extracted_value,
                auto_resolve,
            )
        elif strategy == "set_to_now":
            # Set to current timestamp
            existing_page[field_name] = datetime.now()
            result.changes.append(
                Change(
                    field=field_name,
                    old_value=existing_value,
                    new_value=existing_page[field_name],
                    change_type="updated",
                    timestamp=datetime.now(),
                    reason=f"Updated timestamp using {strategy} strategy",
                )
            )
            result.fields_changed += 1

    def _merge_union(
        self,
        result: IntegrationResult,
        existing_page: dict[str, Any],
        extracted_data: dict[str, Any],
        field_name: str,
        existing_value: Any,
        extracted_value: Any,
    ) -> None:
        """Merge field using union strategy (combine all items).

        Args:
            result: Integration result to update
            existing_page: Existing page data (modified in-place)
            extracted_data: Extracted data
            field_name: Field name
            existing_value: Existing field value
            extracted_value: Extracted field value
        """
        if not isinstance(existing_value, list) or not isinstance(extracted_value, list):
            return

        # Create union - avoid duplicates, preserve order
        merged = list(existing_value)
        for item in extracted_value:
            if not self._item_exists(merged, item):
                merged.append(item)

        if merged != existing_value:
            existing_page[field_name] = merged
            result.changes.append(
                Change(
                    field=field_name,
                    old_value=existing_value,
                    new_value=merged,
                    change_type="merged",
                    timestamp=datetime.now(),
                    reason=f"Merged {len(extracted_value)} items using union strategy",
                )
            )
            result.fields_merged += 1

    def _merge_deduplicate(
        self,
        result: IntegrationResult,
        existing_page: dict[str, Any],
        extracted_data: dict[str, Any],
        field_name: str,
        existing_value: Any,
        extracted_value: Any,
    ) -> None:
        """Merge with deduplication for complex objects.

        Args:
            result: Integration result to update
            existing_page: Existing page data (modified in-place)
            extracted_data: Extracted data
            field_name: Field name
            existing_value: Existing field value
            extracted_value: Extracted field value
        """
        if not isinstance(existing_value, list) or not isinstance(extracted_value, list):
            return

        merged = list(existing_value)
        added_count = 0

        for extracted_item in extracted_value:
            # Check if item already exists (by content, not reference)
            if not self._item_exists(merged, extracted_item):
                merged.append(extracted_item)
                added_count += 1

        if added_count > 0:
            existing_page[field_name] = merged
            result.changes.append(
                Change(
                    field=field_name,
                    old_value=existing_value,
                    new_value=merged,
                    change_type="deduped",
                    timestamp=datetime.now(),
                    reason=f"Deduplicated and added {added_count} unique items",
                )
            )
            result.fields_merged += 1

    def _merge_prefer_newer(
        self,
        result: IntegrationResult,
        existing_page: dict[str, Any],
        extracted_data: dict[str, Any],
        field_name: str,
        existing_value: Any,
        extracted_value: Any,
        auto_resolve: bool,
    ) -> None:
        """Merge preferring newer/higher confidence values.

        Args:
            result: Integration result to update
            existing_page: Existing page data (modified in-place)
            extracted_data: Extracted data
            field_name: Field name
            existing_value: Existing field value
            extracted_value: Extracted field value
            auto_resolve: Whether to auto-resolve conflicts
        """
        # For scalar values, check confidence
        existing_conf = existing_page.get("confidence", 0.5)
        extracted_conf = extracted_data.get("confidence", 1.0)

        # Ensure we have floats
        try:
            existing_conf = float(existing_conf) if existing_conf else 0.5
            extracted_conf = float(extracted_conf) if extracted_conf else 1.0
        except (ValueError, TypeError):
            existing_conf = 0.5
            extracted_conf = 1.0

        conf_diff = extracted_conf - existing_conf

        # If extracted has significantly higher confidence, use it
        if conf_diff > self.CONFIDENCE_THRESHOLD:
            existing_page[field_name] = extracted_value
            result.changes.append(
                Change(
                    field=field_name,
                    old_value=existing_value,
                    new_value=extracted_value,
                    change_type="updated",
                    timestamp=datetime.now(),
                    reason=f"Updated with higher confidence value (diff: {conf_diff:.2f})",
                )
            )
            result.fields_changed += 1
        elif abs(conf_diff) <= self.CONFIDENCE_THRESHOLD and existing_value != extracted_value:
            # Conflict: similar confidence but different values
            conflict = IntegrationConflict(
                field=field_name,
                existing_value=existing_value,
                extracted_value=extracted_value,
                resolution="manual_review" if not auto_resolve else "keep_existing",
                reason=f"Values differ with similar confidence (diff: {conf_diff:.2f})",
                confidence_diff=conf_diff,
            )
            result.conflicts.append(conflict)
            result.conflicts_detected += 1

            # If auto-resolving, keep existing
            if auto_resolve:
                logger.debug(f"Auto-resolving conflict in field {field_name}, keeping existing")

    def _item_exists(self, items: list[Any], item: Any) -> bool:
        """Check if item already exists in list.

        Handles both simple values and dicts (by comparing relevant fields).

        Args:
            items: List to search
            item: Item to find

        Returns:
            True if item exists
        """
        if isinstance(item, dict):
            # For dicts, check if a similar item exists
            # Use name, claim, or other identifying fields
            key_fields = ["name", "claim", "subject", "source_entity", "id"]
            item_keys = {k: v for k, v in item.items() if k in key_fields}

            for existing in items:
                if isinstance(existing, dict):
                    existing_keys = {k: v for k, v in existing.items() if k in key_fields}
                    # Check if key fields match
                    if all(
                        existing_keys.get(k) == item_keys.get(k)
                        for k in set(item_keys.keys()) & set(existing_keys.keys())
                    ):
                        return True
        else:
            # For simple values, direct comparison
            if item in items:
                return True

        return False

    def rollback(self, page_id: str, steps: int = 1) -> IntegrationResult | None:
        """Rollback integration changes.

        Args:
            page_id: Page to rollback
            steps: Number of integration steps to rollback

        Returns:
            Result of the rolled-back state, or None if no history
        """
        if page_id not in self.history or not self.history[page_id]:
            logger.warning(f"No integration history for page {page_id}")
            return None

        if len(self.history[page_id]) < steps:
            logger.warning(f"Cannot rollback {steps} steps for page {page_id}")
            return None

        # Get the state we're rolling back to (before removing states)
        target_index = len(self.history[page_id]) - steps - 1
        if target_index >= 0:
            rollback_result = self.history[page_id][target_index].result
        else:
            # Rolling back past the first state - return the first integration result
            rollback_result = self.history[page_id][0].result

        # Remove the last N states
        for _ in range(steps):
            self.history[page_id].pop()

        return rollback_result

    def get_history(self, page_id: str) -> list[IntegrationState]:
        """Get integration history for a page.

        Args:
            page_id: Page identifier

        Returns:
            List of integration states in chronological order
        """
        return self.history.get(page_id, [])

    def clear_history(self, page_id: str | None = None) -> None:
        """Clear integration history.

        Args:
            page_id: If None, clears all history; otherwise clears history for specific page
        """
        if page_id is None:
            self.history.clear()
        elif page_id in self.history:
            del self.history[page_id]
