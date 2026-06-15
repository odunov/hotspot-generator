"""Extension root shim for Blender."""

from . import hotspot_base_map_generator as _impl

register = _impl.register
unregister = _impl.unregister
