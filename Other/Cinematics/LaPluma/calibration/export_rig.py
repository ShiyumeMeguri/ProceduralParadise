"""
Export a cast member's rig for pose fitting (run inside Blender).

    blender -b -P export_rig.py -- <character.blend> <armature> <out.npz> [hidden object ...]

Writes the bones (names, parents, rest matrices in armature space, lengths),
a sample of the visible skinned vertices (rest positions, their four
strongest bones and weights) and the mesh each sample comes from.  The
pose fit (``fit_pose.py``) poses this rig in PyTorch with the same forward
kinematics Blender uses and compares it with the reference.
"""
import sys

import bpy
import numpy as np

arguments = sys.argv[sys.argv.index("--") + 1:]
path, armature_name, out = arguments[:3]
hidden = set(arguments[3:])
bpy.ops.wm.open_mainfile(filepath=path)
rig = bpy.data.objects[armature_name]
bones = list(rig.data.bones)
names = [bone.name for bone in bones]
index = {name: k for k, name in enumerate(names)}
parents = np.array([index[bone.parent.name] if bone.parent else -1 for bone in bones], np.int32)
rest = np.array([np.array(bone.matrix_local) for bone in bones], np.float64)
lengths = np.array([bone.length for bone in bones], np.float64)
deform = np.array([bone.use_deform for bone in bones], bool)


def descendants(root):
    children = {}
    for obj in bpy.data.objects:
        if obj.parent is not None:
            children.setdefault(obj.parent, []).append(obj)
    found = [root]
    k = 0
    while k < len(found):
        found.extend(children.get(found[k], ()))
        k += 1
    return found


positions, bone_ids, weights, sources = [], [], [], []
mesh_names = []
random = np.random.default_rng(7)
for obj in descendants(rig):
    if obj.type != "MESH" or obj.name in hidden:
        continue
    mesh = obj.data
    groups = {group.index: index.get(group.name, -1) for group in obj.vertex_groups}
    count = len(mesh.vertices)
    take = min(count, max(200, count // 6))
    chosen = random.choice(count, take, replace=False)
    world = np.array(obj.matrix_world)
    rig_inverse = np.linalg.inv(np.array(rig.matrix_world))
    to_rig = rig_inverse @ world
    mesh_index = len(mesh_names)
    mesh_names.append(obj.name)
    for vertex_index in chosen:
        vertex = mesh.vertices[int(vertex_index)]
        pairs = sorted(((element.weight, groups.get(element.group, -1)) for element in vertex.groups
                        if element.weight > 0.0 and groups.get(element.group, -1) >= 0), reverse=True)[:4]
        if not pairs:
            continue
        total = sum(weight for weight, _ in pairs)
        padded = pairs + [(0.0, 0)] * (4 - len(pairs))
        positions.append((to_rig @ np.array([*vertex.co, 1.0]))[:3])
        bone_ids.append([bone for _, bone in padded])
        weights.append([weight / total for weight, _ in padded])
        sources.append(mesh_index)
np.savez_compressed(out, names=np.array(names), parents=parents, rest=rest, lengths=lengths, deform=deform,
                    positions=np.array(positions), bones=np.array(bone_ids, np.int32), weights=np.array(weights),
                    sources=np.array(sources, np.int32), meshes=np.array(mesh_names),
                    rig_matrix=np.array(rig.matrix_world))
print("exported", len(names), "bones,", len(positions), "samples from", mesh_names)
