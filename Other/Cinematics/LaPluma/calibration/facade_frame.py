"""
A match-move (``matchmove.py``) in the measuring frame of the building it saw: X along the
facade, Y into the building, Z up, origin at the reference frame's camera (the shot's
``facade``), the solve's units.

    python facade_frame.py <solve.json> <shot.matchmove.json> <out prefix>

The axes are the building's vertical and the facade's horizontal as the match-move solved them
from every frame's segments.  Writes ``<prefix>_world.json`` (per frame the camera ``position`` and
``rotation_world_from_camera``, OpenCV axes, and the ``focal`` length: what ``stereo.py``
measures the building with and ``set_camera.py`` turns into the set's camera) and
``<prefix>_points.npy`` (the solve's points in the frame).
"""
import argparse
import json

import numpy as np
from scipy.spatial.transform import Rotation

parser = argparse.ArgumentParser()
parser.add_argument("solve")
parser.add_argument("shot")
parser.add_argument("out")
args = parser.parse_args()
solve = json.load(open(args.solve, encoding="utf-8"))
facade = json.load(open(args.shot, encoding="utf-8"))["facade"]
focal = solve["focal"]
origin = np.array(solve["cameras"][str(facade["reference"])]["center"])
reference = Rotation.from_rotvec(solve["cameras"][str(facade["reference"])]["rotvec"]).as_matrix()
x_axis = np.array(solve["along"])
z_axis = np.array(solve["up"])
if (reference @ z_axis)[1] > 0:
    z_axis = -z_axis
if (reference @ x_axis)[2] < 0:
    x_axis = -x_axis
z_axis -= x_axis * (x_axis @ z_axis)
x_axis /= np.linalg.norm(x_axis)
z_axis /= np.linalg.norm(z_axis)
basis = np.stack([x_axis, np.cross(z_axis, x_axis), z_axis])
np.save(args.out + "_points.npy", (np.array(solve["points"]) - origin) @ basis.T)
cameras = {frame: {"position": ((np.array(camera["center"]) - origin) @ basis.T).tolist(),
                   "rotation_world_from_camera": (basis @ Rotation.from_rotvec(camera["rotvec"]).as_matrix().T).tolist()}
           for frame, camera in solve["cameras"].items()}
json.dump({"basis": basis.tolist(), "origin": origin.tolist(), "focal": focal, "cameras": cameras}, open(args.out + "_world.json", "w"))
print("cameras of", len(cameras), "frames in the facade frame ->", args.out + "_world.json")
