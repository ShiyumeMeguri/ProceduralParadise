"""
Other scene builder: things that belong to no world.

With no arguments it builds the default scene -- the shishi-odoshi of the
Props family, fed by a spray wand -- and saves it to the git-ignored
``Build/`` folder (``Build/Props/ShishiOdoshi/ShishiOdoshi.blend``).  The
file opens ready to play: press Space and the simulations run (every scene's
README.md is inside as the text ``Guide``).

* Blender UI: Scripting workspace -> Text Editor -> Open ``Other/build.py``
  -> Run Script.  The scene is built in place and saved.
* Command line (Blender 5.3)::

      blender -b -P Other/build.py
      blender -b -P Other/build.py -- Props/Slime
      blender -b -P Other/build.py -- Props/WaterBalloon --out balloon.blend
      blender -b -P Other/build.py -- Greenhouse/GlassAtrium --render atrium.png
      blender -b -P Other/build.py -- Weapons/Scythe --view hero --render scythe.png
      blender -b -P Other/build.py -- --render still.png

An item folder holding a ``film.json`` is a film (``Cinematics/LaPluma``):
its sets, cast and shots are built by ``Core.film`` and its own options
apply (see that module), e.g.::

      blender -b -P Other/build.py -- Cinematics/LaPluma --render-shots --video

Arguments (all optional)
------------------------
scene                <family>/<item> folder relative to Other/ (default Props/ShishiOdoshi)
--shot NAME          shot in <scene>/shots/ that is the active camera and look
                     (default: scene.json "defaults")
--out PATH           .blend to write (default Build/<Family>/<Scene>/<Scene>.blend)
--no-save            do not write the .blend
--render PATH        render the active shot to PATH (png) at the scene's first frame
--view NAME          render a free view of scene.json "views" instead
--samples N          override the render samples
--scale S            resolution scale (e.g. 0.5 for previews)
--no-look            disable the compositor look
--no-grade           keep the compositor look but leave out its grade
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
                if candidate.endswith(os.path.join("Other", "build.py")) and os.path.isfile(candidate):
                    return os.path.dirname(candidate)
    except ImportError:
        pass
    folder = os.getcwd()
    while True:
        candidate = os.path.join(folder, "Other")
        if os.path.isfile(os.path.join(candidate, "build.py")) and os.path.isdir(os.path.join(candidate, "Props")):
            return candidate
        parent = os.path.dirname(folder)
        if parent == folder:
            raise RuntimeError("Cannot find Other/build.py: open the file itself in Blender's Text Editor "
                               "(Text > Open) or run  blender -P Other/build.py")
        folder = parent


HERE = _locate_here()
ROOT = os.path.dirname(HERE)
BUILD_DIR = os.path.join(ROOT, "Build")
DEFAULT_SCENE = "Props/ShishiOdoshi"
for path in (ROOT, HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

import bpy  # noqa: E402,F401


def parse(argv=None):
    from Core import driver
    return driver.parse(driver.base_parser("Build a scene of things that belong to no world", "scene", DEFAULT_SCENE), argv)


def build_dir(scene_rel):
    """Git-ignored output folder of a scene: Build/<Family>/<Scene>/."""
    parts = scene_rel.replace("\\", "/").strip("/").split("/")
    return os.path.join(BUILD_DIR, parts[0], parts[-1])


def main(argv=None):
    if __name__ == "__main__":
        from Core import driver as stale
        stale.fresh_modules(ROOT)
    from Core import driver, film
    if argv is None:
        arguments = driver.script_args(sys.argv)
    else:
        arguments = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    item = film.target(arguments, DEFAULT_SCENE)
    if film.is_film(os.path.join(HERE, item)):
        return film.run(HERE, ROOT, os.path.join(HERE, "build.py"), arguments)
    args = parse(argv)
    context = driver.build_scene_folder(HERE, args)
    name = os.path.basename(args.scene.rstrip("/\\"))
    out = os.path.abspath(args.out or os.path.join(build_dir(args.scene), f"{name}.blend"))
    return driver.run(context, args, out, ROOT, os.path.join(HERE, "build.py"))


if __name__ == "__main__":
    main()
