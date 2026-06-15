"""Hotspot Base Map Generator Blender extension."""

import importlib
import sys

try:
    import bpy  # type: ignore
except ModuleNotFoundError:  # Allows pure Python tests outside Blender.
    bpy = None


_MODULE_NAMES = (
    "constants",
    "model.layout",
    "model",
    "raster",
    "image_io",
    "properties",
    "operators",
    "ui",
    "overlay",
    "tools",
)


def _load_runtime_modules():
    globals_dict = globals()
    needs_reload = "_runtime_modules_loaded" in globals_dict
    for module_name in _MODULE_NAMES:
        full_name = f"{__name__}.{module_name}"
        if needs_reload and full_name in sys.modules:
            importlib.reload(sys.modules[full_name])
        else:
            importlib.import_module(full_name)

    globals_dict["properties"] = sys.modules[f"{__name__}.properties"]
    globals_dict["operators"] = sys.modules[f"{__name__}.operators"]
    globals_dict["ui"] = sys.modules[f"{__name__}.ui"]
    globals_dict["overlay"] = sys.modules[f"{__name__}.overlay"]
    globals_dict["tools"] = sys.modules[f"{__name__}.tools"]
    globals_dict["_runtime_modules_loaded"] = True


if bpy is not None:
    _load_runtime_modules()


def register():
    if bpy is None:
        raise RuntimeError("Hotspot Base Map Generator must be registered inside Blender.")

    properties.register()
    operators.register()
    ui.register()
    overlay.register()
    tools.register()


def unregister():
    if bpy is None:
        return

    tools.unregister()
    overlay.unregister()
    ui.unregister()
    operators.unregister()
    properties.unregister()


if __name__ == "__main__":
    register()
