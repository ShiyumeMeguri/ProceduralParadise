"""
Export a cast member's rig for pose fitting (run inside Blender).

    blender -b -P export_rig.py -- <character.blend> <armature> <out.npz> [hidden object ...]

Writes the bones (names, parents, rest matrices in armature space, lengths),
a sample of the visible skinned surface, uniform over its area (rest
positions, their four strongest bones and weights, blended across the
triangle a sample lies on) and the mesh and material each sample comes
from (a prop's parts are told apart by their materials).  The pose
fits (``fit_pose.py``, ``fit_prop.py``) pose this rig in PyTorch with the
same forward kinematics Blender uses and compare it with the reference.
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


def vertex_weights(obj, mesh):
    groups = {group.index: index.get(group.name, -1) for group in obj.vertex_groups}
    result = []
    for vertex in mesh.vertices:
        weights = {}
        for element in vertex.groups:
            bone = groups.get(element.group, -1)
            if element.weight > 0.0 and bone >= 0:
                weights[bone] = weights.get(bone, 0.0) + element.weight
        result.append(weights)
    return result


positions, bone_ids, weights, sources, sample_materials = [], [], [], [], []
mesh_names = []
material_names = []
random = np.random.default_rng(7)
rig_inverse = np.linalg.inv(np.array(rig.matrix_world))
for obj in descendants(rig):
    if obj.type != "MESH" or obj.name in hidden:
        continue
    mesh = obj.data
    mesh.calc_loop_triangles()
    count = len(mesh.vertices)
    corners = np.empty(count * 3)
    mesh.vertices.foreach_get("co", corners)
    corners = corners.reshape(-1, 3)
    triangles = np.empty(len(mesh.loop_triangles) * 3, np.int64)
    mesh.loop_triangles.foreach_get("vertices", triangles)
    triangles = triangles.reshape(-1, 3)
    triangle_materials = np.empty(len(mesh.loop_triangles), np.int64)
    mesh.loop_triangles.foreach_get("material_index", triangle_materials)
    slot_names = [slot.material.name if slot.material else "" for slot in obj.material_slots] or [""]
    for name in slot_names:
        if name not in material_names:
            material_names.append(name)
    slot_index = [material_names.index(name) for name in slot_names]
    a, b, c = (corners[triangles[:, slot]] for slot in range(3))
    areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    if len(triangles) == 0 or areas.sum() <= 0.0:
        continue
    take = min(count, max(200, count // 6))
    chosen = random.choice(len(triangles), take, p=areas / areas.sum())
    first, second = random.random(take), random.random(take)
    root = np.sqrt(first)
    barycentric = np.stack([1.0 - root, root * (1.0 - second), root * second], 1)
    points = (barycentric[:, :, None] * corners[triangles[chosen]]).sum(1)
    to_rig = rig_inverse @ np.array(obj.matrix_world)
    per_vertex = vertex_weights(obj, mesh)
    mesh_index = len(mesh_names)
    mesh_names.append(obj.name)
    for sample, triangle, blend, slot in zip(points, triangles[chosen], barycentric, triangle_materials[chosen]):
        blended = {}
        for vertex, share in zip(triangle, blend):
            for bone, weight in per_vertex[int(vertex)].items():
                blended[bone] = blended.get(bone, 0.0) + weight * share
        pairs = sorted(((weight, bone) for bone, weight in blended.items() if weight > 0.0), reverse=True)[:4]
        if not pairs:
            continue
        total = sum(weight for weight, _ in pairs)
        padded = pairs + [(0.0, 0)] * (4 - len(pairs))
        positions.append((to_rig @ np.array([*sample, 1.0]))[:3])
        bone_ids.append([bone for _, bone in padded])
        weights.append([weight / total for weight, _ in padded])
        sources.append(mesh_index)
        sample_materials.append(slot_index[min(int(slot), len(slot_index) - 1)])
np.savez_compressed(out, names=np.array(names), parents=parents, rest=rest, lengths=lengths, deform=deform,
                    positions=np.array(positions), bones=np.array(bone_ids, np.int32), weights=np.array(weights),
                    sources=np.array(sources, np.int32), meshes=np.array(mesh_names),
                    sample_materials=np.array(sample_materials, np.int32), materials=np.array(material_names),
                    rig_matrix=np.array(rig.matrix_world))
print("exported", len(names), "bones,", len(positions), "samples from", mesh_names)
