import unittest
from array import array

from hotspot_base_map_generator.constants import COLOR_MODE_GRAYSCALE, COLOR_MODE_STORED, MASK_MODE_FILL, MASK_MODE_SQUIRCLE, SPLIT_VERTICAL
from hotspot_base_map_generator.model.layout import build_root, derive_leaf_regions, split_node
from hotspot_base_map_generator.raster import (
    bounds_to_pixel_rect,
    render_ao_pixels_from_height,
    render_curvature_pixels_from_height,
    render_edge_pixels_from_leaves,
    render_height_values_from_leaves,
    render_id_pixels_from_leaves,
    render_mask_pixels_from_leaves,
    render_normal_pixels_from_height,
)


def pixel_at(pixels, width, x, y):
    start = (y * width + x) * 4
    return tuple(round(value, 4) for value in pixels[start : start + 4])


class RasterTests(unittest.TestCase):
    def test_bounds_quantization_uses_half_open_rectangles(self):
        nodes = split_node(build_root(), 1, SPLIT_VERTICAL, 0.5)
        leaves = derive_leaf_regions(nodes)

        self.assertEqual(bounds_to_pixel_rect(leaves[0].bounds, 5, 2), (0, 0, 3, 2))
        self.assertEqual(bounds_to_pixel_rect(leaves[1].bounds, 5, 2), (3, 0, 5, 2))

    def test_stored_leaf_colors_fill_regions(self):
        nodes = split_node(build_root(), 1, SPLIT_VERTICAL, 0.5)
        nodes[1] = nodes[1].__class__(**{**nodes[1].__dict__, "color": (1.0, 0.0, 0.0, 1.0)})
        nodes[2] = nodes[2].__class__(**{**nodes[2].__dict__, "color": (0.0, 1.0, 0.0, 1.0)})
        leaves = derive_leaf_regions(nodes)

        pixels = render_id_pixels_from_leaves(leaves, 4, 2, color_mode=COLOR_MODE_STORED)

        self.assertEqual(pixel_at(pixels, 4, 0, 0), (1.0, 0.0, 0.0, 1.0))
        self.assertEqual(pixel_at(pixels, 4, 3, 1), (0.0, 1.0, 0.0, 1.0))

    def test_gutter_insets_rendered_leaf_pixels_only(self):
        nodes = split_node(build_root(), 1, SPLIT_VERTICAL, 0.5)
        nodes[1] = nodes[1].__class__(**{**nodes[1].__dict__, "color": (1.0, 0.0, 0.0, 1.0)})
        nodes[2] = nodes[2].__class__(**{**nodes[2].__dict__, "color": (0.0, 1.0, 0.0, 1.0)})
        leaves = derive_leaf_regions(nodes)

        pixels = render_id_pixels_from_leaves(leaves, 6, 3, color_mode=COLOR_MODE_STORED, gutter_pixels=1)

        self.assertEqual(pixel_at(pixels, 6, 0, 1), (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(pixel_at(pixels, 6, 1, 1), (1.0, 0.0, 0.0, 1.0))
        self.assertEqual(pixel_at(pixels, 6, 3, 1), (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(pixel_at(pixels, 6, 4, 1), (0.0, 1.0, 0.0, 1.0))

    def test_large_gutter_keeps_tiny_regions_visible(self):
        leaves = derive_leaf_regions(build_root())

        pixels = render_id_pixels_from_leaves(leaves, 2, 2, color_mode=COLOR_MODE_STORED, gutter_pixels=10)

        self.assertEqual(pixel_at(pixels, 2, 0, 0), (1.0, 1.0, 1.0, 1.0))

    def test_grayscale_mode_uses_leaf_order(self):
        leaves = derive_leaf_regions(split_node(build_root(), 1, SPLIT_VERTICAL, 0.5))

        pixels = render_id_pixels_from_leaves(leaves, 2, 1, color_mode=COLOR_MODE_GRAYSCALE)

        self.assertEqual(pixel_at(pixels, 2, 0, 0), (0.3333, 0.3333, 0.3333, 1.0))
        self.assertEqual(pixel_at(pixels, 2, 1, 0), (0.6667, 0.6667, 0.6667, 1.0))

    def test_mask_map_fills_guttered_leaf_areas(self):
        leaves = derive_leaf_regions(build_root())

        pixels = render_mask_pixels_from_leaves(leaves, 4, 4, gutter_pixels=1)

        self.assertEqual(pixel_at(pixels, 4, 0, 0), (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(pixel_at(pixels, 4, 1, 1), (1.0, 1.0, 1.0, 1.0))

    def test_mask_squircle_creates_broad_edge_falloff(self):
        leaves = derive_leaf_regions(build_root())

        pixels = render_mask_pixels_from_leaves(leaves, 5, 5, mask_mode=MASK_MODE_SQUIRCLE, mask_size_pixels=1, mask_softness_pixels=0)

        self.assertEqual(pixel_at(pixels, 5, 0, 2), (1.0, 1.0, 1.0, 1.0))
        self.assertEqual(pixel_at(pixels, 5, 2, 2), (0.0, 0.0, 0.0, 1.0))

    def test_mask_max_coverage_prevents_small_island_whiteout(self):
        leaves = derive_leaf_regions(build_root())

        pixels = render_mask_pixels_from_leaves(leaves, 5, 5, mask_mode=MASK_MODE_SQUIRCLE, mask_size_pixels=99, mask_softness_pixels=0, mask_max_coverage=0.4)

        self.assertEqual(pixel_at(pixels, 5, 2, 2), (0.0, 0.0, 0.0, 1.0))

    def test_mask_invert_flips_fill(self):
        leaves = derive_leaf_regions(build_root())

        pixels = render_mask_pixels_from_leaves(leaves, 2, 2, mask_mode=MASK_MODE_FILL, invert=True)

        self.assertEqual(pixel_at(pixels, 2, 1, 1), (0.0, 0.0, 0.0, 1.0))

    def test_edge_map_draws_hard_leaf_borders(self):
        leaves = derive_leaf_regions(split_node(build_root(), 1, SPLIT_VERTICAL, 0.5))

        pixels = render_edge_pixels_from_leaves(leaves, 6, 4, edge_width_pixels=1)

        self.assertEqual(pixel_at(pixels, 6, 0, 1), (1.0, 1.0, 1.0, 1.0))
        self.assertEqual(pixel_at(pixels, 6, 1, 1), (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(pixel_at(pixels, 6, 2, 1), (1.0, 1.0, 1.0, 1.0))
        self.assertEqual(pixel_at(pixels, 6, 3, 1), (1.0, 1.0, 1.0, 1.0))
        self.assertEqual(pixel_at(pixels, 6, 4, 1), (0.0, 0.0, 0.0, 1.0))

    def test_edge_width_changes_thickness(self):
        leaves = derive_leaf_regions(build_root())

        pixels = render_edge_pixels_from_leaves(leaves, 5, 5, edge_width_pixels=2)

        self.assertEqual(pixel_at(pixels, 5, 1, 2), (1.0, 1.0, 1.0, 1.0))
        self.assertEqual(pixel_at(pixels, 5, 2, 2), (0.0, 0.0, 0.0, 1.0))

    def test_height_values_create_bevel_ramp_and_flat_center(self):
        leaves = derive_leaf_regions(build_root())

        values = render_height_values_from_leaves(leaves, 5, 5, base_height=0.0, height_depth=1.0, bevel_width_pixels=2)

        self.assertLess(values[2], values[12])
        self.assertEqual(round(values[12], 4), 1.0)

    def test_normal_from_flat_height_is_neutral(self):
        pixels = render_normal_pixels_from_height(array("f", (0.5,)) * 9, 3, 3)

        self.assertEqual(pixel_at(pixels, 3, 1, 1), (0.5, 0.5, 1.0, 1.0))

    def test_normal_changes_on_height_slope(self):
        values = array("f", (0.0, 0.5, 1.0)) * 3

        pixels = render_normal_pixels_from_height(values, 3, 3, strength=1.0)

        self.assertLess(pixel_at(pixels, 3, 1, 1)[0], 0.5)

    def test_normal_radius_smooths_tiny_height_spikes(self):
        values = array("f", (0.0,)) * 25
        values[12] = 1.0

        sharp = render_normal_pixels_from_height(values, 5, 5, strength=1.0, radius=1)
        smooth = render_normal_pixels_from_height(values, 5, 5, strength=1.0, radius=2)

        self.assertLess(pixel_at(sharp, 5, 1, 2)[0], 0.5)
        self.assertEqual(pixel_at(smooth, 5, 1, 2), (0.5, 0.5, 1.0, 1.0))

    def test_directx_normal_flips_green_channel(self):
        values = array("f", (0.0, 0.0, 0.0, 0.5, 0.5, 0.5, 1.0, 1.0, 1.0))

        opengl = render_normal_pixels_from_height(values, 3, 3, strength=1.0, directx=False)
        directx = render_normal_pixels_from_height(values, 3, 3, strength=1.0, directx=True)

        self.assertAlmostEqual(pixel_at(opengl, 3, 1, 1)[1] + pixel_at(directx, 3, 1, 1)[1], 1.0, places=4)

    def test_ao_darkens_lower_pixels_near_higher_pixels(self):
        pixels = render_ao_pixels_from_height(array("f", (0.0, 1.0, 1.0)), 3, 1, radius=1, strength=1.0)

        self.assertLess(pixel_at(pixels, 3, 0, 0)[0], pixel_at(pixels, 3, 2, 0)[0])

    def test_ao_samples_diagonal_occluders(self):
        values = array("f", (1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 1.0))

        pixels = render_ao_pixels_from_height(values, 3, 3, radius=1, strength=1.0)

        self.assertLess(pixel_at(pixels, 3, 1, 1)[0], 1.0)

    def test_curvature_flat_height_is_neutral(self):
        pixels = render_curvature_pixels_from_height(array("f", (0.5,)) * 25, 5, 5, strength=1.0, radius=1)

        self.assertEqual(pixel_at(pixels, 5, 2, 2), (0.5, 0.5, 0.5, 1.0))

    def test_curvature_convex_height_is_bright(self):
        values = array("f", (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.25, 0.5, 0.25, 0.0, 0.0, 0.5, 1.0, 0.5, 0.0, 0.0, 0.25, 0.5, 0.25, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0))

        pixels = render_curvature_pixels_from_height(values, 5, 5, strength=0.25, radius=1)

        self.assertGreater(pixel_at(pixels, 5, 2, 2)[0], 0.5)

    def test_curvature_concave_height_is_dark(self):
        values = array("f", (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.75, 0.5, 0.75, 1.0, 1.0, 0.5, 0.0, 0.5, 1.0, 1.0, 0.75, 0.5, 0.75, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0))

        pixels = render_curvature_pixels_from_height(values, 5, 5, strength=0.25, radius=1)

        self.assertLess(pixel_at(pixels, 5, 2, 2)[0], 0.5)


if __name__ == "__main__":
    unittest.main()
