import unittest

from hotspot_base_map_generator.constants import SPLIT_HORIZONTAL, SPLIT_VERTICAL
from hotspot_base_map_generator.model.layout import (
    Bounds,
    build_root,
    choose_cut_orientation,
    cursor_split_ratio,
    derive_leaf_regions,
    find_leaf_at_uv,
    grid_preview_ratios,
    grid_subdivide_node,
    is_leaf,
    split_node,
)


class LayoutTests(unittest.TestCase):
    def test_root_starts_as_single_leaf(self):
        nodes = build_root()

        self.assertTrue(is_leaf(nodes, 1))
        leaves = derive_leaf_regions(nodes)

        self.assertEqual(len(leaves), 1)
        self.assertEqual((leaves[0].bounds.x0, leaves[0].bounds.y0, leaves[0].bounds.x1, leaves[0].bounds.y1), (0.0, 0.0, 1.0, 1.0))

    def test_vertical_split_creates_left_and_right_leaves(self):
        nodes = split_node(build_root(), 1, SPLIT_VERTICAL, 0.25)
        leaves = derive_leaf_regions(nodes)

        self.assertEqual([leaf.node_id for leaf in leaves], [2, 3])
        self.assertEqual((leaves[0].bounds.x0, leaves[0].bounds.x1), (0.0, 0.25))
        self.assertEqual((leaves[1].bounds.x0, leaves[1].bounds.x1), (0.25, 1.0))

    def test_horizontal_split_creates_bottom_and_top_leaves(self):
        nodes = split_node(build_root(), 1, SPLIT_HORIZONTAL, 0.75)
        leaves = derive_leaf_regions(nodes)

        self.assertEqual([leaf.node_id for leaf in leaves], [2, 3])
        self.assertEqual((leaves[0].bounds.y0, leaves[0].bounds.y1), (0.0, 0.75))
        self.assertEqual((leaves[1].bounds.y0, leaves[1].bounds.y1), (0.75, 1.0))

    def test_cannot_split_internal_node(self):
        nodes = split_node(build_root(), 1, SPLIT_VERTICAL)

        with self.assertRaises(ValueError):
            split_node(nodes, 1, SPLIT_HORIZONTAL)

    def test_find_leaf_at_uv_hits_root(self):
        leaves = derive_leaf_regions(build_root())

        leaf = find_leaf_at_uv(leaves, 0.25, 0.75)

        self.assertIsNotNone(leaf)
        self.assertEqual(leaf.node_id, 1)

    def test_find_leaf_at_uv_hits_nested_leaf(self):
        nodes = split_node(build_root(), 1, SPLIT_VERTICAL, 0.5)
        nodes = split_node(nodes, 2, SPLIT_HORIZONTAL, 0.5)
        leaves = derive_leaf_regions(nodes)

        leaf = find_leaf_at_uv(leaves, 0.25, 0.75)

        self.assertIsNotNone(leaf)
        self.assertEqual(leaf.node_id, 5)

    def test_find_leaf_at_uv_misses_outside_canvas(self):
        leaves = derive_leaf_regions(build_root())

        self.assertIsNone(find_leaf_at_uv(leaves, -0.01, 0.5))
        self.assertIsNone(find_leaf_at_uv(leaves, 0.5, 1.01))

    def test_find_leaf_at_uv_uses_deterministic_shared_edges(self):
        nodes = split_node(build_root(), 1, SPLIT_VERTICAL, 0.5)
        leaves = derive_leaf_regions(nodes)

        edge_leaf = find_leaf_at_uv(leaves, 0.5, 0.5)
        outer_leaf = find_leaf_at_uv(leaves, 1.0, 1.0)

        self.assertIsNotNone(edge_leaf)
        self.assertEqual(edge_leaf.node_id, 3)
        self.assertIsNotNone(outer_leaf)
        self.assertEqual(outer_leaf.node_id, 3)

    def test_choose_cut_orientation_prefers_vertical_centerline(self):
        orientation = choose_cut_orientation(Bounds(0.0, 0.0, 1.0, 1.0), 0.52, 0.9)

        self.assertEqual(orientation, SPLIT_VERTICAL)

    def test_choose_cut_orientation_prefers_horizontal_centerline(self):
        orientation = choose_cut_orientation(Bounds(0.0, 0.0, 1.0, 1.0), 0.9, 0.52)

        self.assertEqual(orientation, SPLIT_HORIZONTAL)

    def test_choose_cut_orientation_normalizes_non_square_bounds(self):
        orientation = choose_cut_orientation(Bounds(0.0, 0.0, 0.25, 1.0), 0.2, 0.7)

        self.assertEqual(orientation, SPLIT_HORIZONTAL)

    def test_midpoint_snap_returns_half_ratio(self):
        bounds = Bounds(0.0, 0.0, 1.0, 1.0)

        self.assertEqual(cursor_split_ratio(bounds, SPLIT_VERTICAL, 0.25, 0.9, True), 0.5)
        self.assertEqual(cursor_split_ratio(bounds, SPLIT_HORIZONTAL, 0.9, 0.25, True), 0.5)

    def test_unsnapped_cursor_ratio_uses_local_leaf_coordinate(self):
        bounds = Bounds(0.25, 0.1, 0.75, 0.9)

        self.assertAlmostEqual(cursor_split_ratio(bounds, SPLIT_VERTICAL, 0.375, 0.5, False), 0.25)
        self.assertAlmostEqual(cursor_split_ratio(bounds, SPLIT_HORIZONTAL, 0.5, 0.7, False), 0.75)

    def test_unsnapped_cursor_ratio_clamps_near_edges(self):
        bounds = Bounds(0.0, 0.0, 1.0, 1.0)

        self.assertEqual(cursor_split_ratio(bounds, SPLIT_VERTICAL, 0.0, 0.5, False), 0.001)
        self.assertEqual(cursor_split_ratio(bounds, SPLIT_HORIZONTAL, 0.5, 1.0, False), 0.999)

    def test_grid_preview_ratios(self):
        self.assertEqual(grid_preview_ratios(2), [0.5])
        self.assertEqual(grid_preview_ratios(3), [1 / 3, 2 / 3])
        self.assertEqual(grid_preview_ratios(4), [0.25, 0.5, 0.75])

    def test_grid_preview_ratios_reject_invalid_sizes(self):
        with self.assertRaises(ValueError):
            grid_preview_ratios(1)
        with self.assertRaises(ValueError):
            grid_preview_ratios(17)

    def test_grid_subdivide_2x2_creates_row_major_equal_cells(self):
        nodes, cell_ids = grid_subdivide_node(build_root(), 1, 2, 2)
        leaves = derive_leaf_regions(nodes)

        self.assertEqual(cell_ids, [4, 5, 6, 7])
        self.assertEqual([leaf.node_id for leaf in leaves], [4, 5, 6, 7])
        self.assertEqual(
            [(leaf.bounds.x0, leaf.bounds.y0, leaf.bounds.x1, leaf.bounds.y1) for leaf in leaves],
            [
                (0.0, 0.0, 0.5, 0.5),
                (0.5, 0.0, 1.0, 0.5),
                (0.0, 0.5, 0.5, 1.0),
                (0.5, 0.5, 1.0, 1.0),
            ],
        )

    def test_grid_subdivide_1x4_creates_left_to_right_columns(self):
        nodes, cell_ids = grid_subdivide_node(build_root(), 1, 1, 4)
        leaves = derive_leaf_regions(nodes)

        self.assertEqual(cell_ids, [2, 4, 6, 7])
        self.assertEqual(len(leaves), 4)
        self.assertEqual([(leaf.bounds.x0, leaf.bounds.x1) for leaf in leaves], [(0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.0)])

    def test_grid_subdivide_3x1_creates_bottom_to_top_rows(self):
        nodes, cell_ids = grid_subdivide_node(build_root(), 1, 3, 1)
        leaves = derive_leaf_regions(nodes)

        self.assertEqual(cell_ids, [2, 4, 5])
        self.assertEqual(len(leaves), 3)
        self.assertEqual([(round(leaf.bounds.y0, 6), round(leaf.bounds.y1, 6)) for leaf in leaves], [(0.0, 0.333333), (0.333333, 0.666667), (0.666667, 1.0)])

    def test_grid_subdivide_2x3_covers_canvas_without_gaps(self):
        nodes, cell_ids = grid_subdivide_node(build_root(), 1, 2, 3)
        leaves = derive_leaf_regions(nodes)

        self.assertEqual(len(cell_ids), 6)
        self.assertEqual(len(leaves), 6)
        total_area = sum((leaf.bounds.x1 - leaf.bounds.x0) * (leaf.bounds.y1 - leaf.bounds.y0) for leaf in leaves)
        self.assertAlmostEqual(total_area, 1.0)
        self.assertEqual((leaves[0].bounds.x0, leaves[0].bounds.y0), (0.0, 0.0))
        self.assertEqual((leaves[-1].bounds.x1, leaves[-1].bounds.y1), (1.0, 1.0))

    def test_grid_subdivide_rejects_invalid_sizes(self):
        with self.assertRaises(ValueError):
            grid_subdivide_node(build_root(), 1, 1, 1)
        with self.assertRaises(ValueError):
            grid_subdivide_node(build_root(), 1, 0, 2)
        with self.assertRaises(ValueError):
            grid_subdivide_node(build_root(), 1, 2, 17)

    def test_grid_subdivide_rejects_internal_node(self):
        nodes = split_node(build_root(), 1, SPLIT_VERTICAL)

        with self.assertRaises(ValueError):
            grid_subdivide_node(nodes, 1, 2, 2)


if __name__ == "__main__":
    unittest.main()
