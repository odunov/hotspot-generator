"""Blender Image datablock helpers."""

import os

import bpy

from .constants import IMAGE_PREFIX


def safe_name(value):
    return bpy.path.clean_name((value or "").strip()) or "Scene"


def id_image_name(scene):
    return map_image_name(scene, "ID")


def map_image_name(scene, suffix):
    return f"{IMAGE_PREFIX}_{safe_name(scene.name)}_{suffix}"


def ensure_image(name, width, height, float_buffer=False):
    image = bpy.data.images.get(name)
    if image is not None and getattr(image, "is_float", False) != bool(float_buffer):
        bpy.data.images.remove(image)
        image = None
    if image is None:
        image = bpy.data.images.new(name, width=width, height=height, alpha=True, float_buffer=float_buffer)
    elif tuple(image.size) != (width, height):
        image.scale(width, height)

    image.use_fake_user = True
    try:
        image.alpha_mode = "STRAIGHT"
    except Exception:
        pass
    try:
        image.colorspace_settings.name = "Non-Color"
    except Exception:
        pass
    return image


def write_pixels(image, pixels):
    expected = image.size[0] * image.size[1] * 4
    if len(pixels) != expected:
        raise ValueError(f"Pixel buffer length {len(pixels)} does not match image size {expected}")
    image.pixels.foreach_set(pixels)
    image.update()


def show_image_in_context(context, image):
    space = getattr(context, "space_data", None)
    if space is not None and getattr(space, "type", None) == "IMAGE_EDITOR":
        space.image = image


def show_image_in_open_editors(image):
    for window in getattr(bpy.context.window_manager, "windows", []):
        for area in getattr(window.screen, "areas", []):
            if area.type != "IMAGE_EDITOR":
                continue
            for space in area.spaces:
                if space.type == "IMAGE_EDITOR":
                    space.image = image


def export_image_png(image, directory, filename_stem, suffix="ID"):
    directory = bpy.path.abspath(directory or "//")
    os.makedirs(directory, exist_ok=True)
    filename = f"{safe_name(filename_stem)}_{suffix}.png"
    path = os.path.join(directory, filename)

    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    return path
