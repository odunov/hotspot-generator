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

    registered = []
    for module in (properties, operators, ui, gpu_preview, overlay, tools):
        try:
            module.register()
        except Exception:
            for registered_module in reversed(registered):
                registered_module.unregister()
            raise
        registered.append(module)


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
