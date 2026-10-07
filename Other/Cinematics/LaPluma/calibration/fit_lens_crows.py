"""
Crows flying past a shot's lens, fitted to the dark shapes they make in the reference.

    python fit_lens_crows.py <frames dir> <shot.json> <spec.json> <character masks dir> [--write] [--seed-base 300]

A crow passing the lens is too near, too big and too blurred to be followed as a blot (``track_crows.py``): it is one
event of a few frames, named in the spec with a guess of where it is on one of them::

    {"crows": [{"name": "C1", "frames": [492, 496], "frame": 495,
                "guess": {"center": [x, y], "width": pixels, "motion": [dx, dy, growth a frame]}}, ...]}

Each crow flies straight at a steady speed: its centre on its ``frame`` is P0 in the frame of the camera (x right, y
forward, z up), its velocity V (m/s).  It is drawn as an ellipse ``SPAN`` across and ``HEIGHT`` high, soft-edged, and
every frame of its event is matched to the reference's dark pixels (darker than ``DARK``); where the character's
mask shows her (her black clothes) nothing counts.  All crows of the spec are fitted together -- their union against
the dark, as overlap of union and dark over their joint area -- each in turn (Nelder-Mead, three sweeps).  With
``write`` the shot's lens crows are replaced by these: a ``CIN.Birds.Flock`` of one placed in the frame of the shot's
camera on the crow's frame (``camera_frame``), shown over its event, never nearer the lens than ``NEAREST`` metres.
"""
import argparse
import json
import os

import cv2
import numpy as np
from scipy.optimize import minimize

SPAN, HEIGHT, DARK = 0.8, 0.45, 32
WIDTH, HEIGHT_PX = 480, 270
NEAREST = 0.15


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("frames_dir")
    parser.add_argument("shot")
    parser.add_argument("spec")
    parser.add_argument("masks_dir")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--seed-base", type=int, default=300)
    return parser.parse_args()


def main():
    args = _arguments()
    shot = json.load(open(args.shot, encoding="utf-8"))
    spec = json.load(open(args.spec, encoding="utf-8"))
    film = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(args.shot))), "film.json"), encoding="utf-8"))
    focal = shot["camera"]["focal_px"] * WIDTH / film["resolution"][0]
    cx, cy = WIDTH / 2.0, HEIGHT_PX / 2.0
    fps = float(film["fps"])
    frames = sorted({frame for event in spec["crows"] for frame in range(event["frames"][0], event["frames"][1] + 1)})
    targets, counted = {}, {}
    for frame in frames:
        gray = cv2.cvtColor(cv2.imread(os.path.join(args.frames_dir, f"f{frame:04d}.png")), cv2.COLOR_BGR2GRAY)
        dark = (cv2.resize(gray, (WIDTH, HEIGHT_PX), interpolation=cv2.INTER_AREA) < DARK).astype(np.float32)
        nearest = min(range(frame - 6, frame + 7),
                      key=lambda other: (not os.path.isfile(os.path.join(args.masks_dir, f"m{other:04d}.png")), abs(other - frame)))
        mask = cv2.imread(os.path.join(args.masks_dir, f"m{nearest:04d}.png"), cv2.IMREAD_GRAYSCALE)
        her = np.zeros((HEIGHT_PX, WIDTH), np.float32) if mask is None else cv2.dilate(
            (cv2.resize(mask, (WIDTH, HEIGHT_PX), interpolation=cv2.INTER_AREA) > 127).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(np.float32)
        weight = 1.0 - her
        for x0, y0, x1, y1 in film.get("reference", {}).get("masks", []):
            weight[int(y0 * HEIGHT_PX / film["resolution"][1]):int(y1 * HEIGHT_PX / film["resolution"][1]),
                   int(x0 * WIDTH / film["resolution"][0]):int(x1 * WIDTH / film["resolution"][0])] = 0.0
        targets[frame] = dark * weight
        counted[frame] = weight
    ys, xs = np.mgrid[0:HEIGHT_PX, 0:WIDTH].astype(np.float32)

    def drawn(parameters, frame, event):
        if not event["frames"][0] <= frame <= event["frames"][1]:
            return np.zeros((HEIGHT_PX, WIDTH), np.float32)
        x, y, z = parameters[:3] + parameters[3:] * (frame - event["frame"]) / fps
        if y < 0.05:
            return np.zeros((HEIGHT_PX, WIDTH), np.float32)
        u, v = cx + focal * x / y, cy - focal * z / y
        a, b = focal * SPAN * 0.5 / y, focal * HEIGHT * 0.5 / y
        radius = ((xs - u) / a) ** 2 + ((ys - v) / b) ** 2
        return 1.0 / (1.0 + np.exp(np.minimum((radius - 1.0) * 8.0, 60.0)))

    def loss(all_parameters, only=None):
        total = 0.0
        for frame in (frames if only is None else only):
            union = np.zeros((HEIGHT_PX, WIDTH), np.float32)
            for parameters, event in zip(all_parameters, spec["crows"]):
                union = 1.0 - (1.0 - union) * (1.0 - drawn(parameters, frame, event))
            target = targets[frame]
            union = union * counted[frame]
            intersection = (union * target).sum()
            joined = union.sum() + target.sum() - intersection
            total += 1.0 - intersection / max(joined, 1.0) if joined > 50 else 0.0
        return total

    def start(event):
        scale = WIDTH / film["resolution"][0]
        u, v, width = event["guess"]["center"][0] * scale, event["guess"]["center"][1] * scale, event["guess"]["width"] * scale
        y = focal * SPAN / width
        du, dv, grow = event["guess"].get("motion", [0.0, 0.0, 1.0])
        y_next = y / grow
        position = np.array([(u - cx) * y / focal, y, -(v - cy) * y / focal])
        later = np.array([(u + du * scale - cx) * y_next / focal, y_next, -(v + dv * scale - cy) * y_next / focal])
        return np.concatenate([position, (later - position) * fps])

    parameters = [start(event) for event in spec["crows"]]
    print("[lens crows] start loss", round(loss(parameters), 3), "over", len(frames), "frames", flush=True)
    for sweep in range(3):
        for index in range(len(parameters)):
            window = range(spec["crows"][index]["frames"][0], spec["crows"][index]["frames"][1] + 1)

            def single(values, index=index, window=window):
                trial = list(parameters)
                trial[index] = values
                return loss(trial, window)
            parameters[index] = minimize(single, parameters[index], method="Nelder-Mead",
                                         options={"maxiter": 600, "xatol": 1e-3, "fatol": 1e-4}).x
        print("[lens crows] sweep", sweep, "loss", round(loss(parameters), 3), flush=True)
    crows = []
    for fitted, event in zip(parameters, spec["crows"]):
        position, velocity = fitted[:3], fitted[3:]
        speed = float(np.linalg.norm(velocity))
        crows.append({"name": event["name"], "frame": event["frame"], "frames": event["frames"],
                      "origin": [float(value) for value in position], "heading": [float(value) / max(speed, 1e-6) for value in velocity],
                      "speed": speed})
        print("[lens crows]", crows[-1], flush=True)
    if args.write:
        items = [item for item in shot.get("items", []) if not item["name"].startswith("Lens Crow")]
        for seed, crow in enumerate(crows):
            origin = crow["origin"]
            if origin[1] < NEAREST:
                origin = [value * NEAREST / origin[1] for value in origin]
            first, last = crow["frames"]
            items.append({"name": f"Lens Crow {crow['name']}", "asset": "CIN.Birds.Flock", "camera_frame": crow["frame"],
                          "rot": [-90.0, 0.0, 0.0], "shown": [first, last],
                          "inputs": {"Count": 1, "Seed": args.seed_base + seed, "Origin": [round(value, 4) for value in origin],
                                     "Extent": [0.0, 0.0, 0.0], "Heading": [round(value, 4) for value in crow["heading"]], "Spread": 0.0,
                                     "Climb": 0.0, "Speed": max(round(crow["speed"], 3), 0.01), "Speed Spread": 0.0, "Beat": 5.0,
                                     "Glide": 0.0, "Size": 1.3, "Size Spread": 0.0, "Start": float(crow["frame"])}})
        shot["items"] = items
        with open(args.shot, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(shot, indent=1, ensure_ascii=False) + "\n")
        print(f"[lens crows] written {len(crows)} lens crows into {args.shot}", flush=True)


if __name__ == "__main__":
    main()
