"""
A shot's look: the tone curve that carries its renders onto the reference.

    python fit_look.py <frames dir> <shot.json> <render pattern> <mask dir> frame [frame ...]

The renders (``<render pattern>`` with ``{frame}``, e.g. ``renders/raw_{frame}.png``, made
with the shot's view transform and no grade) and the reference frames are compared as
distributions of brightness (``Core.grade.fit_grade_hist`` on their luminance): a tone curve,
the same for red, green and blue, so the render keeps its own colours while taking the
reference's contrast and key -- a curve per channel would push colours the two pictures do not
share (her skin, where the reference shows her coat) wherever the other has more of one.
What is the character's in the reference (``<mask dir>``, ``roto.py``: her coat is not on the
model yet) and the film's watermark are left out of both.  The grade is written into the
shot's ``look`` (``Core.render.compositor``).
"""
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
from Core.grade import fit_grade_hist  # noqa: E402

frames_dir, shot_path, pattern, mask_dir = sys.argv[1:5]
frames = [int(value) for value in sys.argv[5:]]
film = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(shot_path))), "film.json"), encoding="utf-8"))
WEIGHTS = np.array([0.2126, 0.7152, 0.0722])
renders, references = [], []
for frame in frames:
    reference = cv2.cvtColor(cv2.imread(os.path.join(frames_dir, "f%04d.png" % frame)), cv2.COLOR_BGR2RGB).astype(np.float64) / 255.0
    render = cv2.cvtColor(cv2.imread(pattern.format(frame=frame)), cv2.COLOR_BGR2RGB)
    render = cv2.resize(render, (reference.shape[1], reference.shape[0]), interpolation=cv2.INTER_AREA).astype(np.float64) / 255.0
    keep = np.ones(reference.shape[:2], bool)
    mask = cv2.imread(os.path.join(mask_dir, "m%04d.png" % frame), cv2.IMREAD_GRAYSCALE)
    if mask is not None:
        keep &= ~(cv2.dilate(mask, np.ones((31, 31), np.uint8)) > 127)
    for x0, y0, x1, y1 in film.get("reference", {}).get("masks", ()):
        keep[y0:y1, x0:x1] = False
    references.append(reference[keep] @ WEIGHTS)
    renders.append(render[keep] @ WEIGHTS)
luminance = fit_grade_hist(np.repeat(np.concatenate(renders)[:, None, None], 3, 2), np.repeat(np.concatenate(references)[:, None, None], 3, 2))
curve = luminance["curves"]["G"]
grade = {"matrix": np.eye(3).tolist(), "offset": [0.0, 0.0, 0.0], "curves": {name: curve for name in "RGB"}, "highlight_rolloff": True}
shot = json.load(open(shot_path, encoding="utf-8"))
shot.setdefault("look", {})["grade"] = grade
shot.setdefault("notes", []).append(f"Its look (look.grade) is the tone curve of calibration/fit_look.py on frames {frames}.")
open(shot_path, "w", encoding="utf-8", newline="\n").write(json.dumps(shot, indent=1, ensure_ascii=False) + "\n")
print("tone curve", [round(y, 3) for _x, y in curve], "->", shot_path)
