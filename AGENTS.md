# Agent Notes

## Blender

- Blender is installed at `C:\ART\Blender`.
- Use the absolute executable path for local smoke tests and extension commands:
  `C:\ART\Blender\blender.exe`.
- The current Blender 5.1 user extension folder is:
  `C:\Users\User\AppData\Roaming\Blender Foundation\Blender\5.1\extensions\user_default`.

## Local Development And Blender Sync

- Treat `C:\Users\User\Documents\Hotspot` as the source of truth for development.
- Keep code edits local in this repository. Do not edit the installed Blender copy directly.
- Before testing in Blender, reflect repository file changes into:
  `C:\Users\User\AppData\Roaming\Blender Foundation\Blender\5.1\extensions\user_default\hotspot_base_map_generator`.
- Sync direction should be repo to Blender only. Do not reverse-sync from Blender's extension folder back into the repo.
- The Blender extension folder must contain runtime extension files only:
  `blender_manifest.toml`, root `__init__.py`, and `hotspot_base_map_generator\`.
- Do not copy development files into Blender: exclude `.git`, `AGENTS.md`, `README.md`, `tests\`, `tools\`, `__pycache__`, `.pytest_cache`, and other generated artifacts.
- Preferred sync command:
  `powershell -ExecutionPolicy Bypass -File tools\sync_to_blender.ps1`.
- For Blender smoke tests, prefer factory startup so unrelated user add-ons do not affect the run:
  `& 'C:\ART\Blender\blender.exe' --factory-startup --background --python tests\blender_smoke.py`.

## Blender Refresh Workflow

- Do not rely on Blender's Reload Scripts behavior for this add-on. It has been unreliable for toolbar tools, RNA classes, and cached modules.
- The supported development refresh loop is: edit files in this repository, run `tools\sync_to_blender.ps1`, fully relaunch Blender, then test the extension.
- If a brand-new Python module/file is added, also add it to `_MODULE_NAMES` in `hotspot_base_map_generator\__init__.py` so fresh Blender launches import it.
