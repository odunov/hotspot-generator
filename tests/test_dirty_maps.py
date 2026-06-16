import unittest

from hotspot_base_map_generator.constants import (
    DIRTY_ALL_MAPS,
    DIRTY_AO_MAPS,
    DIRTY_CURVATURE_MAPS,
    DIRTY_EDGE_MAPS,
    DIRTY_HEIGHT_MAPS,
    DIRTY_ID_MAPS,
    DIRTY_MASK_MAPS,
    DIRTY_NORMAL_MAPS,
    MAP_KEYS,
)


class DirtyMapTests(unittest.TestCase):
    def test_dirty_groups_are_minimal(self):
        self.assertEqual(DIRTY_ID_MAPS, ("ID",))
        self.assertEqual(DIRTY_EDGE_MAPS, ("EDGE",))
        self.assertEqual(DIRTY_MASK_MAPS, ("MASK",))
        self.assertEqual(DIRTY_NORMAL_MAPS, ("NORMAL",))
        self.assertEqual(DIRTY_AO_MAPS, ("AO",))
        self.assertEqual(DIRTY_CURVATURE_MAPS, ("CURVATURE",))
        self.assertEqual(DIRTY_HEIGHT_MAPS, ("HEIGHT", "NORMAL", "AO", "CURVATURE"))
        self.assertEqual(DIRTY_ALL_MAPS, MAP_KEYS)


if __name__ == "__main__":
    unittest.main()
