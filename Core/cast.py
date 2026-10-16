"""
Core.cast -- characters a scene borrows from a .blend of their own.

A character is made and rigged elsewhere, in a file its author keeps
working on; a build links it to that file, so the scene plays the
character as that file has it -- now and every time the scene is opened
after.  The link is the RuriLinkSync add-on's (it must be enabled): the
character's objects are the scene's own -- their transforms, modifiers,
constraints, poses and actions -- while their data-blocks (meshes,
armatures, the materials an object holds in its own slots) are library
overrides of the author's, the one source they follow.  A part the
author's file itself borrows from another file (a body it overrides from a
shared base) follows that file, as the author's does.  The add-on records
on every object which source it follows, so its panel binds, detaches and
pushes the character as it does one made by hand.

A cast entry is data::

    {"blend": {"environment": "LAPLUMA_BLEND"},   (or "path": an absolute path)
     "armature": "Avatar_LaPluma",               (the rig; every object under it comes along)
     "hidden": ["S_actor_lapluma_cloth_05_lod0", ...],
     "note": "why the hidden parts are hidden"}

The file is named by an environment variable (or a path given on the
command line), never written into the project: it lives on its author's
machine.  Every object parented, directly or not, to the armature comes
with it; ``hidden`` parts are kept but neither drawn nor evaluated -- a
coat that is not rigged yet, say.  Objects outside the rig's hierarchy (the
author's reference meshes, curve tools, lights) are left behind.

A character linked once can play in several shots: each gets a performer
of its own (``instance_character``), copies of the rig and its objects that
share the character's data-blocks and animate apart.
"""
from __future__ import annotations

import hashlib
import os

import bpy

__all__ = ["resolve_blend", "blend_digest", "link_character", "instance_character"]


def resolve_blend(entry, overrides=None, name=None):
    """Absolute path of a cast entry's .blend: a command-line override for
    ``name`` first, then ``blend.path``, then the environment variable
    ``blend.environment``.  Raises when none of them gives an existing
    file."""
    blend = entry["blend"]
    path = (overrides or {}).get(name) or blend.get("path")
    if not path and blend.get("environment"):
        path = os.environ.get(blend["environment"])
        if not path:
            raise RuntimeError(f"cast '{name}': set the environment variable {blend['environment']} "
                               f"to the character's .blend (or pass --cast {name}=<path>)")
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(f"cast '{name}': no .blend at {path!r}")
    return os.path.abspath(path)


def blend_digest(path):
    """Content hash of a character file: frames rendered with one version
    of the character are never mixed with frames of the next."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rename(obj, name):
    """Name ``obj`` ``name``, which nothing else may hold: Blender would quietly give it ``name.001``, and whatever
    finds a character's parts by name would find another's."""
    obj.name = name
    if obj.name != name:
        raise ValueError(f"'{name}' is taken: two casts share a prefix")


def _descendants(root, objects):
    children = {}
    for obj in objects:
        if obj.parent is not None:
            children.setdefault(obj.parent, []).append(obj)
    found = [root]
    index = 0
    while index < len(found):
        found.extend(children.get(found[index], ()))
        index += 1
    return found


DATA_KINDS = ("objects", "meshes", "curves", "hair_curves", "armatures", "materials", "images", "node_groups",
              "textures", "actions", "lights", "cameras", "collections", "shape_keys", "grease_pencils")


def _identities():
    return {(kind, block.name_full) for kind in DATA_KINDS for block in getattr(bpy.data, kind, ())}


def _drop_new_orphans(before):
    """Remove the data-blocks the append brought in that nothing uses any
    more, repeatedly (a removed mesh frees its materials, which free their
    images); data that existed before the append is never touched."""
    while True:
        doomed = [block for kind in DATA_KINDS for block in getattr(bpy.data, kind, ())
                  if (kind, block.name_full) not in before and block.users == 0 and kind != "shape_keys"]
        if not doomed:
            return
        bpy.data.batch_remove(doomed)


def _source(datablock, path):
    """The (file, name) that ``datablock`` -- brought in by an append of ``path`` -- follows: an override's own reference
    (a part the author's file borrows from another), else the data-block of its name in ``path`` (the append's record of
    the name it had there)."""
    override = datablock.override_library
    if override is not None and override.reference is not None and override.reference.library is not None:
        return os.path.abspath(bpy.path.abspath(override.reference.library.filepath)), override.reference.name
    return path, datablock.library_weak_reference.id_name[2:]


def _follow(obj, path, source_name):
    """Make the data of ``obj`` (an object of ``path`` named ``source_name`` there, appended) and the materials it holds in
    its own slots follow their sources through the RuriLinkSync add-on; returns the links it could not mend."""
    from RuriLinkSync import character, linkage
    unresolved = []
    if obj.data is not None and linkage.collection_of(obj.data) is not None:
        data_path, data_name = _source(obj.data, path)
        if obj.data.override_library is None:
            _override, missing = linkage.attach(obj.data, data_path, data_name)
            unresolved += missing
        character.remember_binding(obj, data_path, source_name)
    for slot in getattr(obj, "material_slots", ()):
        material = slot.material
        if slot.link == "OBJECT" and material is not None and material.library is None and material.override_library is None:
            material_path, material_name = _source(material, path)
            _override, missing = linkage.attach(material, material_path, material_name)
            unresolved += missing
    if obj.type == "MESH" and any(slot.link == "OBJECT" for slot in obj.material_slots):
        obj.shiyume_sync_materials = False
    return unresolved


def link_character(path, armature, collection, hidden=(), prefix=None):
    """Bring the rig ``armature`` of ``path`` with every object under it
    into ``collection``, its data following the file (see the module notes).
    The rig's pose is cleared to its rest pose and its action dropped: the
    scene animates it.  ``hidden`` objects are neither drawn nor evaluated.
    With ``prefix`` every object is renamed ``<prefix>.<name>`` (two casts
    from one file keep apart).  Returns ``(armature object, [objects])``."""
    before = {obj.name_full for obj in bpy.data.objects}
    identities = _identities()
    with bpy.data.libraries.load(path, link=False) as (source, target):
        if armature not in source.objects:
            raise KeyError(f"{path}: no object '{armature}'")
        names = [str(name) for name in source.objects]
        target.objects = list(names)
    source_names = {obj: name for name, obj in zip(names, target.objects) if obj is not None}
    appended = list(source_names)
    rig = next(obj for obj, name in source_names.items() if name == armature)
    if rig.type != "ARMATURE":
        raise TypeError(f"{path}: '{armature}' is a {rig.type}, not an armature")
    kept = _descendants(rig, appended)
    leftovers = [obj for obj in appended if obj not in kept]
    if leftovers:
        bpy.data.batch_remove(leftovers)
    missing = set(hidden) - {source_names[obj] for obj in kept}
    if missing:
        raise KeyError(f"{path}: hidden parts {sorted(missing)} are not under '{armature}'")
    unresolved = []
    for obj in kept:
        source_name = source_names[obj]
        collection.objects.link(obj)
        unresolved += _follow(obj, path, source_name)
        if prefix:
            _rename(obj, f"{prefix}.{source_name}")
        if source_name in hidden:
            obj.hide_render = True
            obj.hide_viewport = True
    if unresolved:
        raise RuntimeError(f"{path}: links of the character its overrides could not mend: {unresolved}")
    if rig.animation_data is not None:
        rig.animation_data_clear()
    for bone in rig.pose.bones:
        bone.location = (0.0, 0.0, 0.0)
        bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        bone.rotation_euler = (0.0, 0.0, 0.0)
        bone.scale = (1.0, 1.0, 1.0)
    rig.location = (0.0, 0.0, 0.0)
    rig.rotation_euler = (0.0, 0.0, 0.0)
    rig.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
    rig.scale = (1.0, 1.0, 1.0)
    _drop_new_orphans(identities)
    added = [obj for obj in bpy.data.objects if obj.name_full not in before]
    return rig, added


def _drivers(holder):
    animation = getattr(holder, "animation_data", None) if holder is not None else None
    return list(animation.drivers) if animation is not None else []


def _driver_targets(holder):
    return [target for curve in _drivers(holder) for variable in curve.driver.variables for target in variable.targets]


def _retarget(item, copies):
    """Point the object properties of ``item`` (a modifier, a constraint, a constraint's target)
    that name one of the copied objects at its copy."""
    for prop in item.bl_rna.properties:
        if prop.type != "POINTER" or prop.is_readonly:
            continue
        value = getattr(item, prop.identifier)
        if isinstance(value, bpy.types.Object) and value in copies:
            setattr(item, prop.identifier, copies[value])


def instance_character(rig, objects, collection, prefix, original_prefix):
    """Another performer of a character ``link_character`` brought in:
    copies of ``rig`` and its ``objects`` in ``collection``, each named
    ``<prefix>.<name>`` for the original's ``<original_prefix>.<name>``,
    that animate apart from the originals.  They share the originals'
    meshes, materials and armature; what they refer to among the originals
    -- a parent, a modifier's or a constraint's object, a driver's target
    -- is the copy of it, and a mesh whose drivers read one of them (shape
    keys a bone opens, say) is overridden afresh from the source it follows,
    its drivers reading the copy.
    Returns ``(armature object, [objects])``."""
    copies = {original: original.copy() for original in objects}
    for original, copy in copies.items():
        if not original.name.startswith(f"{original_prefix}."):
            raise ValueError(f"'{original.name}' is not named '{original_prefix}.<name>'")
        _rename(copy, f"{prefix}.{original.name[len(original_prefix) + 1:]}")
        collection.objects.link(copy)
        if copy.parent in copies:
            inverse = copy.matrix_parent_inverse.copy()
            copy.parent = copies[copy.parent]
            copy.matrix_parent_inverse = inverse
        data = copy.data
        if data is not None and any(target.id in copies for holder in (data, getattr(data, "shape_keys", None))
                                    for target in _driver_targets(holder)):
            copy.data = data.override_library.reference.override_create(remap_local_usages=False)
        for holder in (copy, copy.data, getattr(copy.data, "shape_keys", None)):
            for target in _driver_targets(holder):
                if target.id in copies:
                    target.id = copies[target.id]
        for modifier in copy.modifiers:
            _retarget(modifier, copies)
        constraints = list(copy.constraints) + [constraint for bone in (copy.pose.bones if copy.pose else ())
                                                for constraint in bone.constraints]
        for constraint in constraints:
            _retarget(constraint, copies)
            for target in getattr(constraint, "targets", ()):
                _retarget(target, copies)
    return copies[rig], list(copies.values())
