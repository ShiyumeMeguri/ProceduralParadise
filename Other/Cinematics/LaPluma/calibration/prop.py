"""
A prop the cast holds (her scythe), for the fits.

``Prop``: the one bone its mesh is skinned to and its surface in that
bone's rest frame.  Where the picture puts it is a placement in the set
(``placements``: at the model's size; the same picture at any size, the
prop that much larger that much further from the camera).  A held prop
goes where the hand holding it goes: its bone's matrix is the hand bone's
times a grip -- the prop in the hand's frame, its scale the film's size of
it over the model's (``film_scale``; the reference is generated, its scythe
larger than the character sheet's) -- which is what a performance records
(``grips``) and what the film's interpreter hangs on the hand (a Child Of
constraint).
How well a placement's projection fills the prop's silhouette (``silhouette.py``:
the prop's masks and what may hide it, the character) and stays inside it.
``parts``: a prop whose parts look alike in
outline (a blade's arc and a shaft are both long bands) is split by
material, each part filling a silhouette of its own.  Where the model and
the film's prop differ in shape (the film's hub ring is smaller than the
model's disc, its housing smaller), a part fills its silhouette without
being held inside it as hard (the cast profile's part ``precision`` and the
prop's ``rest_precision``): only parts the film draws as the model is
shaped keep a placement from squeezing the rest in.
"""
import numpy as np
import torch

from silhouette import Silhouette
from skeleton import quaternion_from_matrix, quaternion_matrices


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

    def read_placements(self, frame_items):
        """The placements (F, 4, 4) at the model's size recorded in performance frames."""
        placements = torch.eye(4, device=self.device).repeat(len(frame_items), 1, 1)
        placements[:, :3, :3] = quaternion_matrices(torch.tensor([item["placements"][self.name]["rotation"] for item in frame_items],
                                                                 dtype=torch.float64)).float().to(self.device)
        placements[:, :3, 3] = torch.tensor([item["placements"][self.name]["location"] for item in frame_items],
                                            dtype=torch.float32, device=self.device)
        return placements

    def write_placements(self, frame_items, rotations, translations):
        """Record where the picture puts the prop, at the model's size."""
        for item, rotation, translation in zip(frame_items, rotations.cpu().numpy(), translations.cpu().numpy()):
            item.setdefault("placements", {})[self.name] = {"location": [round(float(v), 5) for v in translation],
                                                            "rotation": [round(float(v), 6) for v in quaternion_from_matrix(rotation)]}

    def write_grips(self, frame_items, grips):
        """Record grips (F, 4, 4) -- the prop bone's matrix in the hand bone's frame, a uniform scale in it."""
        for item, grip in zip(frame_items, grips.cpu().numpy()):
            scale = float(np.cbrt(np.linalg.det(grip[:3, :3])))
            item.setdefault("grips", {})[self.name] = {"location": [round(float(v), 5) for v in grip[:3, 3]],
                                                       "rotation": [round(float(v), 6) for v in quaternion_from_matrix(grip[:3, :3] / scale)],
                                                       "scale": round(scale, 5)}


class Part:
    """Some of the prop's points and the silhouette they alone fill (and stay inside, as
    much as ``precision_weight`` says)."""

    def __init__(self, points, silhouette, generator, precision_weight=1.0, search=1200, cover=4000):
        self.points = points
        self.silhouette = silhouette
        self.precision_weight = precision_weight
        self.search_points = points[torch.randperm(len(points), generator=generator)[:search].to(points.device)]
        self.cover_points = points[torch.randperm(len(points), generator=generator)[:cover].to(points.device)]


def parts(prop, prop_profile, directories, masks, occluders, frames, width, height, device, generator):
    """One part per masked part of the prop's profile (``directories``: name -> its masks), held
    inside its silhouette as much as its ``precision`` says, and the rest of the prop filling the
    prop's masks without the parts' (``rest_precision``) -- the whole prop when none is masked."""
    built = []
    taken = torch.zeros(len(prop.points), dtype=torch.bool, device=device)
    for name, directory in directories.items():
        spec = prop_profile["parts"][name]
        chosen = prop.part(spec["materials"])
        built.append(Part(prop.points[chosen], Silhouette(directory, occluders, frames, width, height, device), generator, spec["precision"]))
        taken |= chosen
    built.append(Part(prop.points[~taken], Silhouette(masks, occluders, frames, width, height, device, subtract=list(directories.values())), generator,
                      prop_profile["rest_precision"] if directories else 1.0))
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
