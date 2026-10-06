"""
A prop the cast holds (her scythe), for the fits.

``Prop``: the one bone its mesh is skinned to and its surface in that
bone's rest frame.  A held prop goes where the hand holding it goes: its
bone's matrix is the hand bone's times a grip -- the prop in the hand's
frame -- which is what a performance records (``grips``) and what the
film's interpreter hangs on the hand (a Child Of constraint).  The film's
prop need not be the model's size (the reference is generated, its scythe
larger than the character sheet's); it is matched as the model grown about
the hand by one ``film_scale`` for the shot, so the grip -- the angle the
prop is held at -- is the film's while the prop stays the model's size.
``Silhouette``: a shot's silhouette of the prop (``masks.py``) and of what
may hide it (the character), and how well a placement's projection fills
it and stays inside it.  What it must fill is sampled half inside the
silhouette and half along its outline, so a thin shaft counts by its
length and not by its few pixels, and a part left uncovered keeps pulling
however far away it is.  ``parts``: a prop whose parts look alike in
outline (a blade's arc and a shaft are both long bands) is split by
material, each part filling a silhouette of its own.  Where the model and
the film's prop differ in shape (the film's head is shorter than the
design sheet's), the rest of the prop may be told to fill its silhouette
without being held inside it (``rest_precision``).
"""
import os

import cv2
import numpy as np
import torch

from skeleton import quaternion_from_matrix, quaternion_matrices


def robust(residual, scale):
    squared = (residual / scale) ** 2
    return squared / (squared + 1.0)


class Prop:
    def __init__(self, skeleton, mesh):
        positions, bones, weights = skeleton.samples([mesh])
        held = {int(b) for b, w in zip(bones.flatten().tolist(), weights.flatten().tolist()) if w > 0.0}
        if len(held) != 1:
            raise SystemExit(f"{mesh} is skinned to {len(held)} bones; a held prop has one")
        self.skeleton = skeleton
        self.device = skeleton.device
        self.bone = held.pop()
        self.name = skeleton.names[self.bone]
        homogeneous = torch.cat([positions, torch.ones(len(positions), 1, device=self.device)], 1)
        self.points = (skeleton.inverse_rest[self.bone] @ homogeneous.T).T[:, :3].contiguous()
        self.centre = self.points.mean(0)
        self.materials = np.array(skeleton.material_names([mesh]))

    def part(self, materials):
        """Which of the prop's points are of the named materials."""
        return torch.tensor(np.isin(self.materials, list(materials)), device=self.device)

    def subset(self, count, generator):
        return self.points[torch.randperm(len(self.points), generator=generator)[:count].to(self.device)]

    @staticmethod
    def place(rotation, translation, points):
        """World positions (F, N, 3) of prop points under per-frame placements."""
        return torch.einsum("fij,nj->fni", rotation, points) + translation[:, None, :]

    def read_grips(self, frame_items):
        """The grips (F, 4, 4) recorded in performance frames, or None where one is missing."""
        if not all(self.name in item.get("grips", {}) for item in frame_items):
            return None
        grips = torch.eye(4, device=self.device).repeat(len(frame_items), 1, 1)
        grips[:, :3, :3] = quaternion_matrices(torch.tensor([item["grips"][self.name]["rotation"] for item in frame_items],
                                                            dtype=torch.float64)).float().to(self.device)
        grips[:, :3, 3] = torch.tensor([item["grips"][self.name]["location"] for item in frame_items], dtype=torch.float32, device=self.device)
        return grips

    def read_aims(self, frame_items):
        """The prop's orientations in the set (F, 3, 3) recorded in performance frames, or None."""
        if not all(self.name in item.get("aims", {}) for item in frame_items):
            return None
        return quaternion_matrices(torch.tensor([item["aims"][self.name] for item in frame_items], dtype=torch.float64)).float().to(self.device)

    def write_aims(self, frame_items, rotations):
        """Record the prop's orientation in the set as the picture shows it."""
        for item, rotation in zip(frame_items, rotations.cpu().numpy()):
            item.setdefault("aims", {})[self.name] = [round(float(v), 6) for v in quaternion_from_matrix(rotation)]

    def write_grips(self, frame_items, grips):
        """Record grips (F, 4, 4) -- the prop bone's matrix in the hand bone's frame."""
        for item, grip in zip(frame_items, grips.cpu().numpy()):
            item.setdefault("grips", {})[self.name] = {"location": [round(float(v), 5) for v in grip[:3, 3]],
                                                       "rotation": [round(float(v), 6) for v in quaternion_from_matrix(grip[:3, :3])]}


class Silhouette:
    def __init__(self, masks, occluders, frames, width, height, device, targets=400, subtract=()):
        self.width, self.height, self.device = width, height, device
        outside_maps, cover_targets, grids, centroids, spreads, present = [], [], [], [], [], []
        for frame in frames:
            mask = cv2.imread(os.path.join(masks, "m%04d.png" % frame), cv2.IMREAD_GRAYSCALE)
            mask = mask > 127 if mask is not None else np.zeros((height, width), bool)
            for other in subtract:
                removed = cv2.imread(os.path.join(other, "m%04d.png" % frame), cv2.IMREAD_GRAYSCALE)
                if removed is not None:
                    mask &= removed <= 127
            allowed = mask.copy()
            if occluders:
                occluder = cv2.imread(os.path.join(occluders, "m%04d.png" % frame), cv2.IMREAD_GRAYSCALE)
                if occluder is not None:
                    allowed |= occluder > 127
            allowed = cv2.dilate(allowed.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
            small = cv2.resize(allowed.astype(np.uint8), (width // 2, height // 2), interpolation=cv2.INTER_NEAREST)
            outside_maps.append(cv2.distanceTransform((small == 0).astype(np.uint8), cv2.DIST_L2, 3) * 2.0)
            ys, xs = np.nonzero(mask)
            present.append(len(xs) > 50)
            if len(xs) == 0:
                ys, xs = np.array([height // 2]), np.array([width // 2])
            contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
            outline = np.concatenate([contour[:, 0] for contour in contours]) if contours else np.stack([xs, ys], 1)
            random = np.random.default_rng(frame)
            inner = random.choice(len(xs), targets // 2, replace=len(xs) < targets // 2)
            edge = random.choice(len(outline), targets - targets // 2, replace=len(outline) < targets - targets // 2)
            cover_targets.append(np.concatenate([np.stack([xs[inner], ys[inner]], 1), outline[edge]]).astype(np.float32))
            grids.append(cv2.resize(mask.astype(np.uint8), (width // 8, height // 8), interpolation=cv2.INTER_AREA) > 0)
            centroids.append([float(xs.mean()), float(ys.mean())])
            spreads.append(float(np.sqrt(xs.var() + ys.var())))
        self.outside_maps = torch.tensor(np.array(outside_maps), device=device)
        self.cover_targets = torch.tensor(np.array(cover_targets), device=device)
        self.grids = torch.tensor(np.array(grids), dtype=torch.float32, device=device)
        self.present = torch.tensor(present, dtype=torch.float32, device=device)
        self.centroids = centroids
        self.spreads = spreads

    def outside(self, pixels, slots):
        """Distance (px) of projected points (B, N, 2) outside the allowed silhouette of their
        frames; beyond the picture's edge nothing is known, so nothing is outside there."""
        grid = torch.stack([pixels[..., 0] / (self.width - 1) * 2 - 1, pixels[..., 1] / (self.height - 1) * 2 - 1], -1)
        maps = self.outside_maps[slots][:, None]
        return torch.nn.functional.grid_sample(maps, grid[:, :, None, :], align_corners=True, padding_mode="zeros")[:, 0, :, 0]

    def precision(self, pixels, slots):
        return robust(self.outside(pixels, slots), 20.0).mean(1)

    def gaps(self, pixels, slots):
        """Per silhouette sample, the distance (px) to the nearest projected point."""
        return torch.cdist(self.cover_targets[slots], pixels).min(2).values

    def coverage(self, pixels, slots):
        gaps = self.gaps(pixels, slots)
        return ((torch.sqrt(gaps ** 2 + 16.0) - 4.0) / 20.0).mean(1)


class Part:
    """Some of the prop's points and the silhouette they alone fill (and stay inside, as
    much as ``precision_weight`` says)."""

    def __init__(self, points, silhouette, generator, precision_weight=1.0, search=1200, cover=4000):
        self.points = points
        self.silhouette = silhouette
        self.precision_weight = precision_weight
        self.search_points = points[torch.randperm(len(points), generator=generator)[:search].to(points.device)]
        self.cover_points = points[torch.randperm(len(points), generator=generator)[:cover].to(points.device)]


def parts(prop, specs, masks, occluders, frames, width, height, device, generator, rest_precision=1.0):
    """One part per ``DIR=MATERIAL,MATERIAL`` spec (its own masks), and the rest of the prop
    filling the prop's masks without the parts' -- the whole prop when there are no specs."""
    built = []
    taken = torch.zeros(len(prop.points), dtype=torch.bool, device=device)
    directories = []
    for spec in specs:
        directory, materials = spec.split("=")
        chosen = prop.part(materials.split(","))
        built.append(Part(prop.points[chosen], Silhouette(directory, occluders, frames, width, height, device), generator))
        taken |= chosen
        directories.append(directory)
    built.append(Part(prop.points[~taken], Silhouette(masks, occluders, frames, width, height, device, subtract=directories), generator,
                      rest_precision if specs else 1.0))
    return built


def fitted(prop_parts, project, rotation, translation, slots, searching=False):
    """Precision and coverage of each placement, summed over the prop's parts."""
    precision, coverage = 0.0, 0.0
    for part in prop_parts:
        inner = part.search_points if searching else part.points
        cover = part.search_points if searching else part.cover_points
        precision = precision + part.precision_weight * part.silhouette.precision(project(Prop.place(rotation, translation, inner), slots), slots)
        coverage = coverage + part.silhouette.coverage(project(Prop.place(rotation, translation, cover), slots), slots)
    return precision, coverage
