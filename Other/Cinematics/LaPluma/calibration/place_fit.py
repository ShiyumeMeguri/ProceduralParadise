"""
Where a shot's camera stands in its set, from the picture (numpy, no Blender):

    python place_fit.py <shot> <spec.json> [--samples 30000] [--write]

A camera solved about the origin (its turn alone: the sky shows nothing of where it is) is placed by turning and moving
that turn into the set -- the shot's ``place``: the origin's ``location``, the direction it ``look``s and its ``roll``
(``scenes._shot_place``) -- so that the set's standing buildings, the spec's ``boxes`` ([x0, x1, y0, y1, z0, z1] set
metres), fill the regions of the picture its ``targets`` mark on their frames ({frame: [polygon of pixels, ...]}) and
leave its ``clear`` regions ({frame: [polygon, ...]}) empty, the performer's root (the shot's performance, relative to the camera) staying
near ``near`` (``near_weight`` a metre), the camera travelling at a velocity of its own (``speed``: the most of each of
its parts, metres a second; none without it), turned as the spec's ``turn`` keeps it ([heading, pitch, roll]: the
picture's columns lean as they do; free without it).  Placements are drawn at random within ``heading``, ``pitch`` and
``roll`` (degrees) with her root within ``spread`` metres of ``near``, the best few refined (Nelder-Mead); a root inside
a box is no placement.  With ``write`` the best is written as the shot's place (``calibration/<shot>.place.json``, with the
spec's ``notes``).
"""
import argparse
import json
import math
import os

import cv2
import numpy as np
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation

HERE = os.path.dirname(os.path.abspath(__file__))
FILM = os.path.join(HERE, "..")
SCALE = 0.25
REFINED = 8
FACE_CORNERS = [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]
NEAR_PLANE = 0.1


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("shot")
    parser.add_argument("spec")
    parser.add_argument("--samples", type=int, default=30000)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args()


def _load(path):
    return json.load(open(path, encoding="utf-8"))


class Placement:
    def __init__(self, shot_name, spec):
        film = _load(os.path.join(FILM, "film.json"))
        shot = _load(os.path.join(FILM, "shots", f"{shot_name}.json"))
        self.width, self.height = film["resolution"]
        self.focal = shot["camera"]["focal_px"]
        keys = shot["camera"]["keys"]
        keys = _load(os.path.join(FILM, keys))["keys"] if isinstance(keys, str) else keys
        self.turns = {key["frame"]: Rotation.from_quat([*key["rotation"][1:], key["rotation"][0]]) for key in keys}
        cast_name, cast = next(iter(shot["cast"].items()))
        if cast.get("relative_to") != "camera":
            raise ValueError(f"{shot_name}: {cast_name}'s performance is not relative to the camera")
        frames = {entry["frame"]: entry for entry in _load(os.path.join(FILM, cast["performance"]))["frames"]}
        self.first = min(frames)
        self.root = np.array(frames[self.first]["location"])
        self.fps = film["fps"]
        self.key_first = min(self.turns)
        self.boxes = [np.array(box, float) for box in spec["boxes"]]
        self.faces = [corners[list(face)] for corners in (self._corners(box) for box in self.boxes) for face in FACE_CORNERS]
        self.targets = {int(frame): self._mask(polygon) for frame, polygon in spec["targets"].items()}
        self.clear = {int(frame): self._mask(polygon) for frame, polygon in spec.get("clear", {}).items()}
        self.near = np.array(spec["near"], float)
        self.near_weight = spec.get("near_weight", 0.02)
        self.clear_weight = spec.get("clear_weight", 1.0)

    @staticmethod
    def _corners(box):
        x0, x1, y0, y1, z0, z1 = box
        return np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)])

    def _mask(self, polygons):
        mask = np.zeros((int(self.height * SCALE), int(self.width * SCALE)), np.uint8)
        cv2.fillPoly(mask, [np.round(np.array(polygon, float) * SCALE).astype(np.int32) for polygon in polygons], 1)
        return mask

    def silhouette(self, rotation, location):
        """The boxes as the camera (``rotation`` of its frame in the set, at ``location``) sees them, a mask."""
        mask = np.zeros((int(self.height * SCALE), int(self.width * SCALE)), np.uint8)
        matrix = rotation.as_matrix()
        for face in self.faces:
            local = (face - location) @ matrix
            clipped = []
            for index in range(len(local)):
                a, b = local[index], local[(index + 1) % len(local)]
                if a[2] < -NEAR_PLANE:
                    clipped.append(a)
                if (a[2] < -NEAR_PLANE) != (b[2] < -NEAR_PLANE):
                    clipped.append(a + (-NEAR_PLANE - a[2]) / (b[2] - a[2]) * (b - a))
            if len(clipped) < 3:
                continue
            clipped = np.array(clipped)
            points = np.stack([(self.width / 2 + self.focal * clipped[:, 0] / -clipped[:, 2]) * SCALE,
                               (self.height / 2 - self.focal * clipped[:, 1] / -clipped[:, 2]) * SCALE], 1)
            if np.abs(points).max() > 1e6:
                continue
            cv2.fillPoly(mask, [np.round(points).astype(np.int32)], 1)
        return mask

    @staticmethod
    def rotation(heading, pitch, roll):
        """The place's turn (degrees), as scenes._shot_place builds it."""
        heading, pitch = math.radians(heading), math.radians(pitch)
        look = np.array([math.cos(pitch) * math.cos(heading), math.cos(pitch) * math.sin(heading), math.sin(pitch)])
        upright = np.array([0.0, 0.0, 1.0]) - look * look[2]
        upright /= np.linalg.norm(upright)
        return Rotation.from_matrix(np.stack([np.cross(upright, -look), upright, -look], 1)) * Rotation.from_euler("z", math.radians(roll))

    def inside(self, point):
        return any(box[0] < point[0] < box[1] and box[2] < point[1] < box[3] and box[4] < point[2] < box[5] for box in self.boxes)

    def travelled(self, location, velocity, frame):
        """Where the camera placed at ``location`` stands on ``frame``, travelling at ``velocity``."""
        return location + velocity * ((frame - self.key_first) / self.fps)

    def evaluate(self, heading, pitch, roll, her, velocity=np.zeros(3)):
        """(score, iou, cover of the clear, location) of a placement putting her root at ``her`` on the first frame, the
        camera travelling at ``velocity``."""
        if self.inside(her):
            return None
        place = self.rotation(heading, pitch, roll)
        location = her - (place * self.turns[self.first]).apply(self.root) - velocity * ((self.first - self.key_first) / self.fps)
        iou = np.mean([(drawn & target).sum() / max((drawn | target).sum(), 1)
                       for drawn, target in ((self.silhouette(place * self.turns[frame], self.travelled(location, velocity, frame)), target)
                                             for frame, target in self.targets.items())])
        cover = np.mean([(self.silhouette(place * self.turns[frame], self.travelled(location, velocity, frame)) & region).sum()
                         / max(region.sum(), 1) for frame, region in self.clear.items()]) if self.clear else 0.0
        score = iou - self.clear_weight * cover - self.near_weight * float(np.linalg.norm(her - self.near))
        return score, float(iou), float(cover), location


def main():
    args = _arguments()
    spec = _load(args.spec)
    fit = Placement(args.shot, spec)
    generator = np.random.default_rng(spec.get("seed", 11))
    speed = spec.get("speed", 0.0)
    drawn = []
    fixed = spec.get("turn")
    for _ in range(args.samples):
        heading, pitch, roll = fixed or (generator.uniform(*spec[name]) for name in ("heading", "pitch", "roll"))
        her = fit.near + generator.uniform(-1.0, 1.0, 3) * spec["spread"]
        velocity = generator.uniform(-1.0, 1.0, 3) * speed
        result = fit.evaluate(heading, pitch, roll, her, velocity)
        if result is not None:
            drawn.append((result[0], np.array([heading, pitch, roll, *her, *velocity])))
    drawn.sort(key=lambda item: -item[0])
    best = None
    steps = [4.0, 4.0, 6.0, 1.5, 1.5, 1.5] + [max(speed * 0.25, 1e-3)] * 3
    for _score, start in drawn[:REFINED]:
        def cost(values):
            velocity = np.clip(values[6:], -speed, speed)
            heading, pitch, roll = fixed or values[:3]
            result = fit.evaluate(heading, pitch, roll, np.array(values[3:6]), velocity)
            return 1.0 if result is None else -result[0]
        simplex = np.vstack([start] + [start + step * np.eye(9)[index] for index, step in enumerate(steps)])
        refined = minimize(cost, start, method="Nelder-Mead", options={"maxiter": 900, "initial_simplex": simplex})
        velocity = np.clip(refined.x[6:], -speed, speed)
        if fixed:
            refined.x[:3] = fixed
        result = fit.evaluate(refined.x[0], refined.x[1], refined.x[2], np.array(refined.x[3:6]), velocity)
        if result is not None:
            print(f"[place] score {result[0]:.3f} iou {result[1]:.3f} clear covered {result[2]:.3f} heading {refined.x[0]:+.1f} "
                  f"pitch {refined.x[1]:+.1f} roll {refined.x[2]:+.1f} her {np.round(refined.x[3:6], 2).tolist()} "
                  f"velocity {np.round(velocity, 2).tolist()} camera {np.round(result[3], 2).tolist()}", flush=True)
            if best is None or result[0] > best[0][0]:
                best = (result, refined.x, velocity)
    (score, _iou, _cover, location), values, velocity = best
    heading, pitch = math.radians(values[0]), math.radians(values[1])
    place = {"notes": spec["notes"], "location": [round(float(value), 3) for value in location],
             "look": [round(math.cos(pitch) * math.cos(heading), 6), round(math.cos(pitch) * math.sin(heading), 6), round(math.sin(pitch), 6)],
             "roll": round(float(values[2]), 2)}
    if speed > 0.0:
        place["velocity"] = [round(float(value), 3) for value in velocity]
    print(f"[place] best {score:.3f}: {json.dumps(place)}", flush=True)
    if args.write:
        path = os.path.join(HERE, f"{args.shot}.place.json")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(place, indent=1, ensure_ascii=False) + "\n")
        print(f"[place] written into {path}", flush=True)


if __name__ == "__main__":
    main()
