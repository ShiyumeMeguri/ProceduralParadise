"""
A cast member's cloth written as the RuriClothPhysics add-on's own payload, set up on the rig as it stands.

    blender -b <character.blend> --addons RuriClothPhysics -P author_cloth.py -- <spec.json> <payload.json>

``spec.json`` names the rig, the capsules on its bones (bone: radius in metres) and the chains (``chains``: a name, the add-on's
connection ``mode``, the ``capsules`` they collide with -- ``"all"`` or bone names -- and their ``roots``: bone names, or the
bones hanging from one bone whose names match a pattern, ``{"children_of", "matching"}``, case aside).  The set-up lives only in
this session (the character file is not saved); a root the rig lacks is refused.
"""
import json
import re
import sys

import bpy
from RuriClothPhysics.blender_host import collider_geom, config_io, operators

spec_path, out = sys.argv[sys.argv.index("--") + 1:sys.argv.index("--") + 3]
spec = json.load(open(spec_path, encoding="utf-8"))
rig = bpy.data.objects[spec["rig"]]
scene = bpy.context.scene
view_layer = bpy.context.view_layer
view_layer.objects.active = rig
settings = rig.ruri_cloth_physics
settings.configs.clear()
collection = collider_geom.collection_for(scene, rig, create=True)
capsules = {}
for bone_name, radius in spec["capsules"].items():
    pose_bone = rig.pose.bones[bone_name]
    start, end = operators._make_capsule(bpy.context, collection, bone_name, rig.matrix_world @ pose_bone.head,
                                         rig.matrix_world @ pose_bone.tail, radius)
    collider_geom.attach_to_bone(view_layer, start, rig, bone_name)
    collider_geom.attach_to_bone(view_layer, end, rig, bone_name)
    capsules[bone_name] = start


def roots(chain):
    named = chain["roots"]
    if isinstance(named, dict):
        return sorted(child.name for child in rig.data.bones[named["children_of"]].children
                      if re.search(named["matching"], child.name, re.IGNORECASE))
    missing = [name for name in named if name not in rig.data.bones]
    if missing:
        raise KeyError(f"{spec_path}: chain '{chain['name']}' roots {missing} are not bones of {rig.name}")
    return named


for chain in spec["chains"]:
    config = settings.configs.add()
    config.name = chain["name"]
    config.connection_mode = chain["mode"]
    for root in roots(chain):
        config.root_bones.add().bone = root
    for bone_name in (list(capsules) if chain["capsules"] == "all" else chain["capsules"]):
        operators._reference_collider(config, capsules[bone_name])
    print(f"[cloth] {chain['name']}: roots {[item.bone for item in config.root_bones]}")
payload = config_io.serialize(settings, config_io.SCOPE_OBJECT, scene)
config_io.save(out, payload)
print("[cloth] wrote", out, "configs", len(payload["settings"]["configs"]), "colliders", len(payload["colliders"]))
