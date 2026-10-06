"""
A shot's camera in the set's metres, as the film reads it (``calibration/<shot>.camera.json``).

    python set_camera.py <facade_world.json> <shot.matchmove.json> <out camera.json>

The cameras in the facade's measuring frame (``facade_frame.py``) go into the set by the
shot's ``set`` data: ``metres`` per solve unit (from the building measured in the frame: its
floors and columns against the set's), the measuring-frame point that is the set's origin
(``origin``) and the set height of that point (``floor``).  Keys: per frame the camera's
``location`` and ``rotation`` (w, x, y, z; Blender's camera looks down its -Z, Y up), and the
``focal_px``.
"""
import argparse
import json

import numpy as np
from scipy.spatial.transform import Rotation

parser = argparse.ArgumentParser()
parser.add_argument("world")
parser.add_argument("shot")
parser.add_argument("out")
args = parser.parse_args()
world = json.load(open(args.world, encoding="utf-8"))
placement = json.load(open(args.shot, encoding="utf-8"))["set"]
origin = np.array(placement["origin"])
lift = np.array([0.0, 0.0, placement["floor"]])
opencv_to_blender = np.diag([1.0, -1.0, -1.0])
keys = []
for frame in range(placement["first"], placement["last"] + 1):
    camera = world["cameras"].get(str(frame))
    if camera is None:
        continue
    location = (np.array(camera["position"]) - origin) * placement["metres"] + lift
    x, y, z, w = Rotation.from_matrix(np.array(camera["rotation_world_from_camera"]) @ opencv_to_blender).as_quat()
    keys.append({"frame": frame, "location": [round(float(v), 5) for v in location],
                 "rotation": [round(float(w), 7), round(float(x), 7), round(float(y), 7), round(float(z), 7)]})
json.dump({"focal_px": world["focal"], "keys": keys}, open(args.out, "w"), indent=1)
print("keys", len(keys), "->", args.out)
