"""Extension root shim for Blender.

Blender extensions expect the register/unregister entry points beside
blender_manifest.toml. The implementation lives in the package below so it can
also be imported by tests and tooling.
"""

import importlib

if "_impl" in locals():
    _impl = importlib.reload(_impl)
else:
    from . import hotspot_base_map_generator as _impl

register = _impl.register
unregister = _impl.unregister
