"""Hotspot Base Map Generator Blender extension."""

try:
    import bpy  # type: ignore
except ModuleNotFoundError:  # Allows pure Python tests outside Blender.
    bpy = None

if bpy is not None:
    from . import gpu_preview, operators, overlay, properties, tools, ui


def register():
    if bpy is None:
        raise RuntimeError("Hotspot Base Map Generator must be registered inside Blender.")

    properties.register()
    operators.register()
    ui.register()
    gpu_preview.register()
    overlay.register()
    tools.register()


def unregister():
    if bpy is None:
        return

    tools.unregister()
    overlay.unregister()
    gpu_preview.unregister()
    ui.unregister()
    operators.unregister()
    properties.unregister()


if __name__ == "__main__":
    register()
