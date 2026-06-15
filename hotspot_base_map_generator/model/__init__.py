"""Pure Python layout model for Hotspot Base Map Generator."""

from .layout import (
    Bounds,
    LeafRegion,
    NodeRecord,
    build_root,
    choose_cut_orientation,
    clamp_split_ratio,
    cursor_split_ratio,
    derive_leaf_regions,
    find_leaf_at_uv,
    find_node,
    grid_preview_ratios,
    grid_subdivide_node,
    is_leaf,
    next_node_id,
    split_node,
    validate_grid_dimensions,
)

__all__ = [
    "Bounds",
    "LeafRegion",
    "NodeRecord",
    "build_root",
    "choose_cut_orientation",
    "clamp_split_ratio",
    "cursor_split_ratio",
    "derive_leaf_regions",
    "find_leaf_at_uv",
    "find_node",
    "grid_preview_ratios",
    "grid_subdivide_node",
    "is_leaf",
    "next_node_id",
    "split_node",
    "validate_grid_dimensions",
]
