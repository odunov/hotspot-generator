ADDON_ID = "hotspot_base_map_generator"
DISPLAY_NAME = "Hotspot Base Map Generator"
IMAGE_PREFIX = "HBMG"

SPLIT_NONE = "NONE"
SPLIT_HORIZONTAL = "HORIZONTAL"
SPLIT_VERTICAL = "VERTICAL"

COLOR_MODE_RANDOM = "RANDOM"
COLOR_MODE_GRAYSCALE = "GRAYSCALE"
COLOR_MODE_STORED = "STORED"

MASK_MODE_FILL = "FILL"
MASK_MODE_OVAL = "OVAL"
MASK_MODE_SQUIRCLE = "SQUIRCLE"

MAP_KEYS = ("ID", "EDGE", "MASK", "HEIGHT", "NORMAL", "AO", "CURVATURE")
HEIGHT_DERIVED_MAP_KEYS = ("HEIGHT", "NORMAL", "AO", "CURVATURE")
MAP_SUFFIXES = {"ID": "ID", "EDGE": "Edge", "MASK": "Mask", "HEIGHT": "Height", "NORMAL": "Normal", "AO": "AO", "CURVATURE": "Curvature"}
MAP_IMAGE_ATTRS = {
    "ID": "id_image_name",
    "EDGE": "edge_image_name",
    "MASK": "mask_image_name",
    "HEIGHT": "height_image_name",
    "NORMAL": "normal_image_name",
    "AO": "ao_image_name",
    "CURVATURE": "curvature_image_name",
}
MAP_EXPORT_ATTRS = {
    "ID": "export_id",
    "EDGE": "export_edge",
    "MASK": "export_mask",
    "HEIGHT": "export_height",
    "NORMAL": "export_normal",
    "AO": "export_ao",
    "CURVATURE": "export_curvature",
}

DIRTY_ALL_MAPS = MAP_KEYS
DIRTY_ID_MAPS = ("ID",)
DIRTY_EDGE_MAPS = ("EDGE",)
DIRTY_MASK_MAPS = ("MASK",)
DIRTY_HEIGHT_MAPS = HEIGHT_DERIVED_MAP_KEYS
DIRTY_NORMAL_MAPS = ("NORMAL",)
DIRTY_AO_MAPS = ("AO",)
DIRTY_CURVATURE_MAPS = ("CURVATURE",)
