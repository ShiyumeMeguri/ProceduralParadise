"""
FractalWorld scene builder.

With no arguments it builds the default scene -- the crystal conservatory
of Crystal Fantasy with a camera for every hero shot, the free views and the
showcase flight -- and saves it to the git-ignored ``Build/`` folder
(``Build/CrystalFantasy/Conservatory/Conservatory.blend``).

* Blender UI: Scripting workspace -> Text Editor -> Open
  ``FractalWorld/build.py`` -> Run Script.  The scene is built in place and
  saved; switch cameras freely (every hero shot is a ``CAM_<shot>``, every
  free view a ``VIEW_<name>``), press Space to watch the butterflies, motes,
  petals and ripples move.
* Command line (Blender 5.3)::

      blender -b -P FractalWorld/build.py
      blender -b -P FractalWorld/build.py -- --render pool.png
      blender -b -P FractalWorld/build.py -- --shot VitrineGallery --render gallery.png
      blender -b -P FractalWorld/build.py -- --view overlook --render overlook.png
      blender -b -P FractalWorld/build.py -- --render-animation

Arguments (all optional)
------------------------
scene                scene folder relative to FractalWorld/ (default CrystalFantasy/Scenes/Conservatory)
--shot NAME          hero shot in <scene>/shots/ that is the active camera and look
                     (default: scene.json "defaults")
--animation NAME     camera flight in <scene>/animations/ ("none" to skip)
--out PATH           .blend to write (default Build/<Realm>/<Scene>/<Scene>.blend)
--no-save            do not write the .blend
--render PATH        render the active shot to PATH (png)
--view NAME          render a free view of scene.json "views" instead
--render-animation [PATH]  render the flight's missing frames and assemble the MP4
--samples N          override Cycles samples
--scale S            resolution scale (e.g. 0.5 for previews)
--no-look            disable the compositor look
"""
from __future__ import annotations

import os
import sys


def _locate_here():
    """Folder of this script however it is run: ``blender -P`` / ``python``
    (real ``__file__``) or Blender's Text Editor (the text data-block knows
    the file)."""
    path = globals().get("__file__")
    if path and os.path.isfile(path):
        return os.path.dirname(os.path.abspath(path))
    try:
        import bpy
        for text in [getattr(getattr(bpy.context, "space_data", None), "text", None)] + list(bpy.data.texts):
            if text is not None and text.filepath:
                candidate = os.path.abspath(bpy.path.abspath(text.filepath))
                if candidate.endswith(os.path.join("FractalWorld", "build.py")) and os.path.isfile(candidate):
                    return os.path.dirname(candidate)
    except ImportError:
        pass
    folder = os.getcwd()
    while True:
        candidate = os.path.join(folder, "FractalWorld")
        if os.path.isfile(os.path.join(candidate, "build.py")) and os.path.isdir(os.path.join(candidate, "Fractals")):
            return candidate
        parent = os.path.dirname(folder)
        if parent == folder:
            raise RuntimeError("Cannot find FractalWorld/build.py: open the file itself in Blender's Text Editor "
                               "(Text > Open) or run  blender -P FractalWorld/build.py")
        folder = parent


HERE = _locate_here()
ROOT = os.path.dirname(HERE)
BUILD_DIR = os.path.join(ROOT, "Build")
DEFAULT_SCENE = "CrystalFantasy/Scenes/Conservatory"
for path in (ROOT, HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

import bpy  # noqa: E402,F401


def parse(argv=None):
    from Core import driver
    return driver.parse(driver.base_parser("Build a FractalWorld procedural scene", "scene", DEFAULT_SCENE), argv)


def build_dir(scene_rel):
    """Git-ignored output folder of a scene: Build/<Realm>/<Scene>/."""
    parts = scene_rel.replace("\\", "/").strip("/").split("/")
    return os.path.join(BUILD_DIR, parts[0], parts[-1])


def build(args):
    from Core import driver
    return driver.build_scene_folder(HERE, args)


def main(argv=None):
    if __name__ == "__main__":
        from Core import driver as stale
        stale.fresh_modules(ROOT)
    from Core import driver
    args = parse(argv)
    context = build(args)
    name = os.path.basename(args.scene.rstrip("/\\"))
    out = os.path.abspath(args.out or os.path.join(build_dir(args.scene), f"{name}.blend"))
    return driver.run(context, args, out, ROOT, os.path.join(HERE, "build.py"))


if __name__ == "__main__":
    main()
