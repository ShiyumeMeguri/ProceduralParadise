"""
A shot's silhouette of one object (``roto.py``) for the fits: what projected points must stay
inside and what they must fill.

``Silhouette``: per frame, how far a projected point lies outside the object's mask (and what
may hide the object -- the character in front of her scythe, the scythe in front of her), the
mask itself (where the object is seen), and samples it must be filled at -- half inside, half
along its outline, so a thin shaft counts by its length and not by its few pixels, and a part
left uncovered keeps pulling however far away it is.  A frame without a mask (the object out
of the picture or not tracked there) holds nothing in or out: ``present`` says which frames
count.
"""
import os

import cv2
import numpy as np
import torch


def robust(residual, scale):
    squared = (residual / scale) ** 2
    return squared / (squared + 1.0)


class Silhouette:
    def __init__(self, masks, occluders, frames, width, height, device, targets=400, subtract=()):
        self.width, self.height, self.device = width, height, device
        outside_maps, inside_maps, cover_targets, grids, centroids, spreads, present = [], [], [], [], [], [], []
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
            inside_maps.append(cv2.resize(mask.astype(np.float32), (width // 2, height // 2), interpolation=cv2.INTER_AREA))
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
        self.inside_maps = torch.tensor(np.array(inside_maps), device=device)
        self.cover_targets = torch.tensor(np.array(cover_targets), device=device)
        self.grids = torch.tensor(np.array(grids), dtype=torch.float32, device=device)
        self.present = torch.tensor(present, dtype=torch.float32, device=device)
        self.centroids = centroids
        self.spreads = spreads

    def _sample(self, maps, pixels, slots):
        """Bilinear samples (zero beyond the edge) of frame ``slots``' maps at pixels (B, N, 2),
        read in place: a search scoring thousands of placements of one frame never copies its map."""
        _, rows, columns = maps.shape
        x = pixels[..., 0] * (columns - 1) / (self.width - 1)
        y = pixels[..., 1] * (rows - 1) / (self.height - 1)
        left, top = x.floor(), y.floor()
        across, down = x - left, y - top
        flat = maps.reshape(-1)
        base = slots[:, None] * (rows * columns)

        def at(column, row):
            inside = ((column >= 0) & (column <= columns - 1) & (row >= 0) & (row <= rows - 1)).float()
            return flat[base + row.clamp(0, rows - 1).long() * columns + column.clamp(0, columns - 1).long()] * inside

        return (at(left, top) * (1 - across) * (1 - down) + at(left + 1, top) * across * (1 - down)
                + at(left, top + 1) * (1 - across) * down + at(left + 1, top + 1) * across * down)

    def outside(self, pixels, slots):
        """Distance (px) of projected points (B, N, 2) outside the allowed silhouette of their
        frames; beyond the picture's edge nothing is known, so nothing is outside there."""
        return self._sample(self.outside_maps, pixels, slots)

    def inside(self, pixels, slots):
        """How much of the object is seen at projected points (B, N, 2): 1 on it, 0 off it."""
        return self._sample(self.inside_maps, pixels, slots)

    def precision(self, pixels, slots):
        return robust(self.outside(pixels, slots), 20.0).mean(1)

    def gaps(self, pixels, slots):
        """Per silhouette sample, the distance (px) to the nearest projected point."""
        return torch.cdist(self.cover_targets[slots], pixels).min(2).values

    def coverage(self, pixels, slots):
        gaps = self.gaps(pixels, slots)
        return ((torch.sqrt(gaps ** 2 + 16.0) - 4.0) / 20.0).mean(1)
