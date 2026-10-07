"""
The crows a shot's reference shows (``track_crows.py``), each flown straight through the set as the shot's camera saw it.

    blender -b --factory-startup -P fit_crows.py -- <tracks.json> <shot> [--seen 0.4] [--size 1.0] [--write]

Every followed crow is one bird of the shot (``Crow <n>``, a ``CIN.Birds.Flock`` of one).  On each frame it was seen,
the shot's camera -- built by the film's own builder -- casts the ray through its centre, and its size in the picture
says how far along the ray it was: a crow of ``size`` shows ``seen`` metres across (the square root of the area it
darkens, wings and all, as the film's crow does on the average beat and turn), so it stands ``seen`` x the lens's
focal length in pixels / the square root of its area away.  Its flight is the straight line, at a steady speed,
nearest to every frame's sighting -- across the rays held hard, along them (the size, which the beating wings make
wobble) loosely, and no faster than the sightings ask (``STEADY``: a crow seen on a few frames, its distance
guessed from a wobbling size, would otherwise dart at a hundred metres a second).  What was not a crow is left out:
a blot whose ray meets the standing set on most of its frames (a dark part of a building), or that hardly moves in
the picture for half a second and more (an edge of something the masks missed), or that hangs in the air slower than
``SLOWEST`` m/s (a crow does not hover; a dark fold of the dust does).  With ``write`` the shot's fitted
crows are replaced by these, each flying through the whole shot: where the reference lost it -- behind her arm, out of
the picture, too blurred to tell -- it flies on.
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sky_reads  # noqa: E402

ACROSS, ALONG, STEADY = 1.0, 0.15, 0.08
STILL_FRAMES, STILL_SHARE, SLOWEST = 15, 0.02, 2.0


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("tracks")
    parser.add_argument("shot")
    parser.add_argument("--seen", type=float, default=0.4)
    parser.add_argument("--size", type=float, default=1.0)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:])


def _perpendiculars(direction):
    helper = np.array([0.0, 0.0, 1.0]) if abs(direction[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    first = np.cross(direction, helper)
    first /= np.linalg.norm(first)
    return first, np.cross(direction, first)


def fly(reads, crow, seen, fps):
    """The straight flight (place on the middle frame, velocity in m/s) nearest to the crow's sightings, and how many of
    its rays meet the standing set."""
    middle = crow["frames"][len(crow["frames"]) // 2]
    rows, targets, weights = [], [], []
    met = 0
    for frame, (x, y), area in zip(crow["frames"], crow["centres"], crow["areas"]):
        origin, direction, focal = reads.ray(frame, x, y)
        depth = seen * focal / np.sqrt(area)
        met += int(reads.hidden_by_set(origin, direction[None, None, :], np.ones((1, 1), bool), depth * 3.0)[0, 0])
        moment = (frame - middle) / fps
        for axis, weight, target in ((direction, ALONG, depth), *((side, ACROSS, 0.0) for side in _perpendiculars(direction))):
            rows.append(np.concatenate([axis, axis * moment]))
            targets.append(target + float(axis @ origin))
            weights.append(weight)
    for axis in np.eye(3):
        rows.append(np.concatenate([np.zeros(3), axis * STEADY]))
        targets.append(0.0)
        weights.append(1.0)
    weights = np.sqrt(np.array(weights))
    solution = np.linalg.lstsq(np.array(rows) * weights[:, None], np.array(targets) * weights, rcond=None)[0]
    return middle, solution[:3], solution[3:], met


def main():
    args = _arguments()
    tracks = json.load(open(args.tracks, encoding="utf-8"))
    reads = sky_reads.ShotSky(args.shot)
    fps = reads.film["fps"]
    seen = args.seen * args.size
    birds = []
    for number, crow in enumerate(tracks["crows"]):
        centres = np.array(crow["centres"])
        travel = float(np.max(np.linalg.norm(centres - centres[0], axis=1)))
        if len(crow["frames"]) >= STILL_FRAMES and travel < STILL_SHARE * reads.width:
            print(f"[crows] {number}: still for {len(crow['frames'])} frames -- not a crow", flush=True)
            continue
        middle, place, velocity, met = fly(reads, crow, seen, fps)
        if met * 2 > len(crow["frames"]):
            print(f"[crows] {number}: on the set {met} of {len(crow['frames'])} frames -- not a crow", flush=True)
            continue
        speed = float(np.linalg.norm(velocity))
        if speed < SLOWEST:
            print(f"[crows] {number}: hangs at {speed:.1f} m/s -- not a crow", flush=True)
            continue
        birds.append({"frames": [crow["frames"][0], crow["frames"][-1]], "middle": middle, "place": place.tolist(),
                      "heading": (velocity / max(speed, 1e-6)).tolist(), "speed": speed})
        print(f"[crows] {number}: frames {crow['frames'][0]}-{crow['frames'][-1]} at {np.round(place, 1)} "
              f"{speed:.1f} m/s", flush=True)
    print(f"[crows] {args.shot}: {len(birds)} crows of {len(tracks['crows'])} followed", flush=True)
    if args.write:
        path = os.path.join(sky_reads.FILM, "shots", f"{args.shot}.json")
        shot = json.load(open(path, encoding="utf-8"))
        items = [item for item in shot.get("items", []) if not item["name"].startswith("Crow ")]
        first, last = shot["frames"]
        for number, bird in enumerate(birds):
            items.append({"name": f"Crow {number + 1}", "asset": "CIN.Birds.Flock", "shown": [first, last],
                          "inputs": {"Count": 1, "Seed": 200 + number, "Origin": [round(value, 3) for value in bird["place"]],
                                     "Extent": [0.0, 0.0, 0.0], "Heading": [round(value, 4) for value in bird["heading"]],
                                     "Spread": 0.0, "Climb": 0.0, "Speed": round(bird["speed"], 3), "Speed Spread": 0.0,
                                     "Size": args.size, "Size Spread": 0.0, "Start": float(bird["middle"])}})
        shot["items"] = items
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(shot, indent=1, ensure_ascii=False) + "\n")
        print(f"[crows] written {len(birds)} crows into {path}", flush=True)


if __name__ == "__main__":
    main()
