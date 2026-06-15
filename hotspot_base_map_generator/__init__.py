"""Hotspot Base Map Generator Blender extension."""

try:
    import bpy  # type: ignore
except ModuleNotFoundError:  # Allows pure Python tests outside Blender.
    bpy = None

if bpy is not None:
    from . import operators, overlay, properties, tools, ui


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
