"""Event Annotation Service for chart overlay markers.

Filters events from the ForwardPriceEngine EventRegistry and provides
annotation data for frontend time-series chart overlays. Supports event
clustering when multiple events fall within the same visual pixel range.

Design decisions:
- Direct reference to EventRegistry (no duplicate storage)
- Supports COAL_CLOSURE, BESS_COMMISSIONING, NETWORK_AUGMENTATION event types
- Returns empty list for regions with no events (graceful degradation)
- Clustering uses day-based proximity derived from pixel_threshold

Requirements: 4.1, 4.2, 4.5, 11.1, 11.2, 11.3, 11.4, 11.5, 17.6
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date, timedelta
from typing import List, Optional, Union

from models.forward_price_models import (
    EventConfidence,
    EventRegistry,
    EventType,
    SupplyDemandEvent,
)
from models.narrative_models import EventAnnotation, EventCluster

logger = logging.getLogger(__name__)

# Supported event types for annotation overlay
SUPPORTED_EVENT_TYPES = frozenset(
    {
        EventType.COAL_CLOSURE,
        EventType.BESS_COMMISSIONING,
        EventType.NETWORK_AUGMENTATION,
    }
)

# Default chart assumptions for pixel-to-days conversion
# A typical 20-year chart at ~800px width → ~9 days/pixel
_DEFAULT_DAYS_PER_PIXEL = 9


class EventAnnotationService:
    """事件标注过滤服务。

    Provides filtered and clustered event annotations for frontend chart
    overlays. References the ForwardPriceEngine EventRegistry directly
    without duplicating event storage.
    """

    def __init__(self, event_registry: EventRegistry) -> None:
        """Initialize with a reference to the event registry.

        Args:
            event_registry: The ForwardPriceEngine's event registry.
                            Referenced directly, not copied.
        """
        self.event_registry = event_registry

    def get_annotations(
        self,
        region: str,
        start_year: int,
        end_year: int,
        event_types: Optional[List[EventType]] = None,
    ) -> List[EventAnnotation]:
        """获取指定区域和时间范围的事件标注。

        Filters events from the registry by region, year range, and
        optionally by event type. Returns empty list if no matching
        events exist (no error raised per Requirement 17.6).

        Args:
            region: NEM region code (e.g. "NSW1") or "WEM".
            start_year: Inclusive start year for filtering.
            end_year: Inclusive end year for filtering.
            event_types: Optional list of event types to include.
                         If None, all supported types are included.

        Returns:
            List of EventAnnotation objects matching the filter criteria.
            Empty list if no events match.
        """
        # Default to all supported types if not specified
        allowed_types = (
            set(event_types) & SUPPORTED_EVENT_TYPES
            if event_types is not None
            else SUPPORTED_EVENT_TYPES
        )

        annotations: List[EventAnnotation] = []

        for event in self.event_registry.events:
            # Filter by region
            if event.region != region:
                continue

            # Filter by year range
            event_year = event.expected_date.year
            if event_year < start_year or event_year > end_year:
                continue

            # Filter by event type
            if event.event_type not in allowed_types:
                continue

            # Convert SupplyDemandEvent → EventAnnotation
            annotations.append(self._to_annotation(event))

        return annotations

    def cluster_annotations(
        self,
        annotations: List[EventAnnotation],
        pixel_threshold: int = 20,
    ) -> List[Union[EventAnnotation, EventCluster]]:
        """聚类相近事件为单一标记。

        Events within the same pixel range on a chart are merged into
        an EventCluster. The pixel_threshold is converted to a day-based
        proximity using chart dimension assumptions.

        Property 6 guarantee: the sum of all cluster sizes plus
        unclustered individual events equals the original annotation count.

        Args:
            annotations: List of event annotations to cluster.
            pixel_threshold: Number of pixels within which events
                             are considered overlapping. Default 20.

        Returns:
            Mixed list of individual EventAnnotation (for isolated events)
            and EventCluster (for grouped events).
        """
        if not annotations:
            return []

        # Convert pixel threshold to day proximity
        day_threshold = pixel_threshold * _DEFAULT_DAYS_PER_PIXEL

        # Sort by date for sequential clustering
        sorted_annotations = sorted(annotations, key=lambda a: a.date)

        # Greedy sequential clustering
        clusters: List[Union[EventAnnotation, EventCluster]] = []
        current_group: List[EventAnnotation] = [sorted_annotations[0]]

        for annotation in sorted_annotations[1:]:
            # Check if this annotation is within threshold of the group start
            group_start_date = current_group[0].date
            days_apart = (annotation.date - group_start_date).days

            if days_apart <= day_threshold:
                current_group.append(annotation)
            else:
                # Flush current group
                clusters.append(self._finalize_group(current_group))
                current_group = [annotation]

        # Flush last group
        clusters.append(self._finalize_group(current_group))

        return clusters

    def _to_annotation(self, event: SupplyDemandEvent) -> EventAnnotation:
        """Convert a SupplyDemandEvent to an EventAnnotation."""
        return EventAnnotation(
            event_name=event.name,
            event_type=event.event_type,
            region=event.region,
            date=event.expected_date,
            capacity_mw=event.capacity_mw,
            confidence=event.confidence,
            spread_impact_factor=event.spread_impact_factor,
            description=None,
        )

    def _finalize_group(
        self, group: List[EventAnnotation]
    ) -> Union[EventAnnotation, EventCluster]:
        """Convert a group of annotations to either a single annotation or a cluster."""
        if len(group) == 1:
            return group[0]

        # Calculate center date as the midpoint between first and last
        first_date = group[0].date
        last_date = group[-1].date
        center_offset = (last_date - first_date).days // 2
        center_date = first_date + timedelta(days=center_offset)

        # Determine dominant type by frequency
        type_counts = Counter(a.event_type for a in group)
        dominant_type = type_counts.most_common(1)[0][0]

        return EventCluster(
            center_date=center_date,
            event_count=len(group),
            events=group,
            dominant_type=dominant_type,
        )
