import unittest

from hotspot_base_map_generator.constants import COLOR_MODE_STORED, SPLIT_VERTICAL
from hotspot_base_map_generator.model.layout import build_root, derive_leaf_regions, split_node
from hotspot_base_map_generator.raster import bounds_to_pixel_rect, render_id_pixels_from_leaves


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


if __name__ == "__main__":
    unittest.main()

