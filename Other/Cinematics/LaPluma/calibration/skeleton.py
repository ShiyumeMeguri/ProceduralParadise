"""
The cast's rig in PyTorch, posed the way Blender poses it.

A bone's world matrix is its parent's world matrix times its rest offset
times its local (pose) matrix; a root bone hangs off the rig object.  The
rig comes from ``export_rig.py``: bone names, parents, rest matrices in rig
space, lengths, and skinned samples of the cast's surface.
"""
import math

import numpy as np
import torch


def quaternion_matrices(quaternions):
    """(..., 4) w, x, y, z -> (..., 3, 3)."""
    w, x, y, z = quaternions.unbind(-1)
    return torch.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w),
                        2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w),
                        2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1).reshape(*w.shape, 3, 3)


def axis_angle_matrices(vector):
    angle = vector.norm(dim=-1, keepdim=True).clamp(min=1e-8)
    axis = vector / angle
    x, y, z = axis.unbind(-1)
    zero = torch.zeros_like(x)
    cross = torch.stack([zero, -z, y, z, zero, -x, -y, x, zero], -1).reshape(*vector.shape[:-1], 3, 3)
    eye = torch.eye(3, device=vector.device).expand(cross.shape)
    sin = torch.sin(angle)[..., None]
    cos = torch.cos(angle)[..., None]
    return eye + sin * cross + (1 - cos) * (cross @ cross)


def quaternion_from_matrix(m):
    trace = m[0, 0] + m[1, 1] + m[2, 2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        return [0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s]
    if m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        return [(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s]
    if m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        return [(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s]
    s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
    return [(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s]


class Skeleton:
    def __init__(self, path, device):
        rig = np.load(path)
        self.device = device
        self.names = [str(name) for name in rig["names"]]
        self.index = {name: k for k, name in enumerate(self.names)}
        self.parents = [int(parent) for parent in rig["parents"]]
        self.rest = torch.tensor(rig["rest"], dtype=torch.float32, device=device)
        self.inverse_rest = torch.linalg.inv(self.rest)
        self.lengths = torch.tensor(rig["lengths"], dtype=torch.float32, device=device)
        self.offsets = [self.rest[b] if parent < 0 else torch.linalg.inv(self.rest[parent]) @ self.rest[b]
                        for b, parent in enumerate(self.parents)]
        self.meshes = [str(name) for name in rig["meshes"]]
        self.sources = rig["sources"]
        self.positions = rig["positions"]
        self.bones = rig["bones"]
        self.weights = rig["weights"]
        self.materials = [str(name) for name in rig["materials"]]
        self.sample_materials = rig["sample_materials"]

    def depth(self, bone):
        count = 0
        while self.parents[bone] >= 0:
            bone = self.parents[bone]
            count += 1
        return count

    def ancestry(self, bones):
        """``bones`` and all their ancestors, parents first."""
        needed = set()
        for bone in bones:
            k = int(bone)
            while k >= 0 and k not in needed:
                needed.add(k)
                k = self.parents[k]
        return sorted(needed, key=lambda b: (self.depth(b), b))

    def pose(self, object_matrix, local, bones):
        """World matrices (F, 4, 4) of ``bones`` (an ``ancestry``): ``local(b)`` is a bone's
        local matrix (F, 4, 4), or None where it rests."""
        world = {}
        for b in bones:
            parent = self.parents[b]
            base = object_matrix @ self.offsets[b] if parent < 0 else world[parent] @ self.offsets[b]
            matrix = local(b)
            world[b] = base if matrix is None else base @ matrix
        return world

    def samples(self, meshes):
        """The skinned samples of ``meshes``: rest positions, bones and weights."""
        chosen = np.isin(np.array(self.meshes)[self.sources], list(meshes))
        return (torch.tensor(self.positions[chosen], dtype=torch.float32, device=self.device),
                torch.tensor(self.bones[chosen], dtype=torch.long, device=self.device),
                torch.tensor(self.weights[chosen], dtype=torch.float32, device=self.device))

    def material_names(self, meshes):
        """The material of each skinned sample of ``meshes`` (in ``samples`` order)."""
        chosen = np.isin(np.array(self.meshes)[self.sources], list(meshes))
        return [self.materials[index] for index in self.sample_materials[chosen]]

    def skin(self, world, positions, bones, weights, frames):
        """Posed positions (F, N, 3) of skinned samples."""
        eye = torch.eye(4, device=self.device).repeat(frames, 1, 1)
        matrices = torch.stack([world[b] if b in world else eye for b in range(len(self.names))], 1)
        skinning = matrices @ self.inverse_rest[None]
        homogeneous = torch.cat([positions, torch.ones(len(positions), 1, device=self.device)], 1)
        total = torch.zeros(frames, len(positions), 3, device=self.device)
        for slot in range(4):
            transform = skinning[:, bones[:, slot]]
            moved = torch.einsum("fnij,nj->fni", transform, homogeneous)[..., :3]
            total = total + moved * weights[None, :, slot, None]
        return total


class Camera:
    """A shot's solved camera (``calibration/<shot>.camera.json``) on chosen frames."""

    def __init__(self, path, frames, width, height, device):
        import json
        data = json.load(open(path, encoding="utf-8"))
        keys = {key["frame"]: key for key in data["keys"]}
        self.focal = float(data["focal_px"])
        self.width, self.height = width, height
        self.rotation = quaternion_matrices(torch.tensor([keys[f]["rotation"] for f in frames], dtype=torch.float64)).float().to(device)
        self.location = torch.tensor([keys[f]["location"] for f in frames], dtype=torch.float32, device=device)

    def project(self, points):
        """points (F, N, 3) world -> pixels (F, N, 2), depth (F, N)."""
        local = torch.einsum("fij,fnj->fni", self.rotation.transpose(1, 2), points - self.location[:, None, :])
        depth = -local[..., 2]
        safe = depth.clamp(min=0.05)
        u = self.width / 2 + self.focal * local[..., 0] / safe
        v = self.height / 2 - self.focal * local[..., 1] / safe
        return torch.stack([u, v], -1), depth
