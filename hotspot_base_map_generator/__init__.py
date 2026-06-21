"""Hotspot Base Map Generator Blender extension."""

try:
    import bpy  # type: ignore
except ModuleNotFoundError:  # Allows pure Python tests outside Blender.
    bpy = None

if bpy is not None:
    from . import gpu_preview, operators, overlay, properties, tools, ui

    _MODULES = (properties, operators, ui, gpu_preview, overlay, tools)


def register():
    if bpy is None:
        raise RuntimeError("Hotspot Base Map Generator must be registered inside Blender.")

    registered = []
    try:
        for module in _MODULES:
            module.register()
            registered.append(module)
    except Exception:
        for registered_module in reversed(registered):
            try:
                registered_module.unregister()
            except Exception:
                pass
        raise


def unregister():
    if bpy is None:
        return

    for module in reversed(_MODULES):
        try:
            module.unregister()
        except Exception:
            pass


if __name__ == "__main__":
    register()
