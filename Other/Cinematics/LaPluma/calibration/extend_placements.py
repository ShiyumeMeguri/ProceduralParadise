"""
Carry a prop's placements back over a shot's opening frames.

    python extend_placements.py <placements.json> <pose.json> <first> <span> <out.json>

The silhouette search (``fit_prop.py``) can read a prop end for end where
the picture alone does not tell its two ends apart -- a shaft running out of
the picture at a corner looks the same nearer at one end or at the other --
and settle on one reading for a shot's opening frames and the other for the
rest.  Placed from ``first`` on (``placements.json``), the prop is carried
back to the shot's earlier frames at the pace of its first ``span`` frames:
its place along the same step a frame, its turn the same turn a frame.  The
earlier frames' poses come from ``pose.json`` (their grips are dropped: the
pose fit hangs the prop anew).
"""
import json
import sys

import numpy as np
from scipy.spatial.transform import Rotation

source, pose_path, out = sys.argv[1], sys.argv[2], sys.argv[5]
first, span = int(sys.argv[3]), int(sys.argv[4])
placed = json.load(open(source, encoding="utf-8"))
poses = {item["frame"]: item for item in json.load(open(pose_path, encoding="utf-8"))["frames"]}
by_frame = {item["frame"]: item for item in placed["frames"]}
name = next(iter(by_frame[first]["placements"]))


def placement(frame):
    record = by_frame[frame]["placements"][name]
    w, x, y, z = record["rotation"]
    return np.array(record["location"]), Rotation.from_quat([x, y, z, w])


start_location, start_rotation = placement(first)
end_location, end_rotation = placement(first + span)
step_location = (end_location - start_location) / span
step_turn = (start_rotation.inv() * end_rotation).as_rotvec() / span
earlier = sorted(frame for frame in poses if frame < first)
frames = []
for frame in earlier:
    k = frame - first
    rotation = start_rotation * Rotation.from_rotvec(step_turn * k)
    x, y, z, w = rotation.as_quat()
    item = dict(poses[frame])
    item.pop("grips", None)
    item["placements"] = {name: {"location": [round(float(v), 5) for v in start_location + step_location * k],
                                 "rotation": [round(float(v), 6) for v in (w, x, y, z)]}}
    frames.append(item)
placed["frames"] = frames + [by_frame[frame] for frame in sorted(by_frame) if frame >= first]
json.dump(placed, open(out, "w", encoding="utf-8"), indent=1)
print("carried", name, "back over", earlier[0] if earlier else None, "-", earlier[-1] if earlier else None, "from", first, "->", out)
