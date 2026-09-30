"""
Open each built .blend on its own and check it is complete: every object's
geometry evaluates, the scene has a camera, and nothing points at a file
outside the .blend (images, libraries, fonts, sounds...).

    python .github/scripts/check_blend.py A.blend [B.blend ...] [--render out_dir]

``--render`` also renders every file's active camera at a small size (a
smoke test that the materials and geometry nodes survived the round trip).
Runs with the ``bpy`` module or ``blender -b -P``.  Exit status 1 on problems.
"""
import os
import sys

import bpy


def external_paths():
    """(datablock, path) for every datablock that reads a file from disk."""
    out = []
    for kind in ("images", "libraries", "fonts", "sounds", "movieclips", "volumes", "cache_files"):
        for d in getattr(bpy.data, kind):
            path = getattr(d, "filepath", "")
            if not path or getattr(d, "packed_file", None) is not None:
                continue
            if kind == "fonts" and path == "<builtin>":
                continue
            if kind == "images" and d.source in {"GENERATED", "VIEWER"}:
                continue
            out.append((d.name, path))
    return out


def triangles_by_object(dg):
    """Triangles every mesh object puts in the render: its own evaluated
    mesh plus the geometry it instances (scattered plants are instances of
    other objects, reported by the depsgraph under their emitter)."""
    own = {}
    counts = {}
    for inst in dg.object_instances:
        source = inst.object
        if source.type != "MESH":
            continue
        key = source.original.name if not inst.is_instance else inst.parent.original.name
        if source.name not in own:
            me = source.to_mesh()
            me.calc_loop_triangles()
            own[source.name] = len(me.loop_triangles)
            source.to_mesh_clear()
        counts[key] = counts.get(key, 0) + own[source.name]
    return counts


def check(path, render_dir=None):
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(path))
    sc = bpy.context.scene
    problems = []
    if sc.camera is None:
        problems.append("the scene has no camera")
    for name, fp in external_paths():
        problems.append(f"external file: {name} -> {fp}")
    dg = bpy.context.evaluated_depsgraph_get()
    counts = triangles_by_object(dg)
    n_obj = n_tri = 0
    empty = []
    for ob in sc.objects:
        if ob.type != "MESH" or not ob.visible_get():
            continue
        n_obj += 1
        tris = counts.get(ob.name, 0)
        n_tri += tris
        if tris == 0 and not ob.hide_render:
            empty.append(ob.name)
    if empty:
        problems.append(f"{len(empty)} mesh objects evaluate to nothing: {', '.join(empty[:8])}")
    mats = sum(1 for m in bpy.data.materials if m.users)
    groups = sum(1 for g in bpy.data.node_groups if g.bl_idname == "GeometryNodeTree")
    print(f"{os.path.basename(path)}: Blender {bpy.app.version_string}, scenes {len(bpy.data.scenes)}, "
          f"mesh objects {n_obj}, triangles {n_tri}, materials {mats}, geometry node groups {groups}, "
          f"camera {sc.camera.name if sc.camera else '-'}, frames {sc.frame_start}-{sc.frame_end}")
    if render_dir:
        r = sc.render
        r.resolution_percentage = 20
        sc.cycles.samples = 8
        r.filepath = os.path.join(render_dir, os.path.splitext(os.path.basename(path))[0] + ".png")
        bpy.ops.render.render(write_still=True)
    for p in problems:
        print("  PROBLEM:", p)
    return not problems


def main(argv):
    render_dir = None
    if "--render" in argv:
        i = argv.index("--render")
        render_dir = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
        os.makedirs(render_dir, exist_ok=True)
    ok = all([check(p, render_dir) for p in argv])
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]))
