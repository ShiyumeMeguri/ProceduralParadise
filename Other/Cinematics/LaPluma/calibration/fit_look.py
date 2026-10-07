"""
A shot's look: the tone curve that carries its renders onto the reference.

    python fit_look.py <frames dir> <shot.json> <render pattern> <mask dir> frame [frame ...] [--render-masks <pattern>]

The renders (``<render pattern>`` with ``{frame}``, e.g. ``renders/raw_{frame}.png``, made
with the shot's look but no grade: ``Core/film.py --no-grade``, so its exposure is in them) and
the reference frames are compared as
distributions of brightness (``Core.grade.fit_grade_hist`` on their luminance): a tone curve
on brightness alone (``curves`` ``"L"``), so the render keeps its own hues and saturation while
taking the reference's contrast and key -- a curve per channel would push colours the two
pictures do not share (her skin) wherever the other has more of one, and even one curve on each
channel saturates what its steep midtones pass.
What is the character's in the reference (``<mask dir>``, ``roto.py``) and in the render (``--render-masks``: the
render's mattes of the cast, alpha the cast: her coat is still being made and stands larger than the reference's) and the
film's watermark are left out of both: where one picture shows her and the other sky, the curve would be bent to lift
the sky.  So is what is darker than ``DARKEST`` in either picture: crows across the lens, the scythe, the shade of her
coat -- more of them in one picture than the other bent the curve to crush the darks; the curve is fitted on the sky and
the set, and below the darkest the render keeps it runs straight to black.  The grade is written into the
shot's ``look`` (``Core.render.compositor``).
"""
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
from Core.grade import fit_grade_hist  # noqa: E402

arguments = sys.argv[1:]
render_masks = None
if "--render-masks" in arguments:
    where = arguments.index("--render-masks")
    render_masks = arguments[where + 1]
    arguments = arguments[:where] + arguments[where + 2:]
frames_dir, shot_path, pattern, mask_dir = arguments[:4]
frames = [int(value) for value in arguments[4:]]
film = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(shot_path))), "film.json"), encoding="utf-8"))
WEIGHTS = np.array([0.2126, 0.7152, 0.0722])
DARKEST = 0.12
renders, references = [], []
for frame in frames:
    reference = cv2.cvtColor(cv2.imread(os.path.join(frames_dir, "f%04d.png" % frame)), cv2.COLOR_BGR2RGB).astype(np.float64) / 255.0
    render = cv2.cvtColor(cv2.imread(pattern.format(frame=frame)), cv2.COLOR_BGR2RGB)
    render = cv2.resize(render, (reference.shape[1], reference.shape[0]), interpolation=cv2.INTER_AREA).astype(np.float64) / 255.0
    keep = np.ones(reference.shape[:2], bool)
    mask = cv2.imread(os.path.join(mask_dir, "m%04d.png" % frame), cv2.IMREAD_GRAYSCALE)
    if mask is not None:
        keep &= ~(cv2.dilate(mask, np.ones((31, 31), np.uint8)) > 127)
    if render_masks is not None:
        matte = cv2.imread(render_masks.format(frame=frame), cv2.IMREAD_UNCHANGED)
        alpha = cv2.resize(matte[:, :, 3], (reference.shape[1], reference.shape[0]), interpolation=cv2.INTER_NEAREST)
        keep &= ~(cv2.dilate(alpha, np.ones((31, 31), np.uint8)) > 127)
    for x0, y0, x1, y1 in film.get("reference", {}).get("masks", ()):
        keep[y0:y1, x0:x1] = False
    keep &= (reference @ WEIGHTS >= DARKEST) & (render @ WEIGHTS >= DARKEST)
    references.append(reference[keep] @ WEIGHTS)
    renders.append(render[keep] @ WEIGHTS)
luminance = fit_grade_hist(np.repeat(np.concatenate(renders)[:, None, None], 3, 2), np.repeat(np.concatenate(references)[:, None, None], 3, 2))
curve = luminance["curves"]["G"]
lowest = float(np.min(np.concatenate(renders)))
at_lowest = float(np.interp(lowest, [x for x, _y in curve], [y for _x, y in curve]))
curve = [[x, x / lowest * at_lowest if x < lowest else y] for x, y in curve]
grade = {"matrix": np.eye(3).tolist(), "offset": [0.0, 0.0, 0.0], "curves": {"L": curve}, "highlight_rolloff": True}
shot = json.load(open(shot_path, encoding="utf-8"))
shot.setdefault("look", {})["grade"] = grade
NOTE = "Its look (look.grade) is the tone curve of calibration/fit_look.py on frames"
shot["notes"] = [note for note in shot.get("notes", []) if not note.startswith(NOTE)] + [f"{NOTE} {frames}."]
open(shot_path, "w", encoding="utf-8", newline="\n").write(json.dumps(shot, indent=1, ensure_ascii=False) + "\n")
print("tone curve", [round(y, 3) for _x, y in curve], "->", shot_path)
