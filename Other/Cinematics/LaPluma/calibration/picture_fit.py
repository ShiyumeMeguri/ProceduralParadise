"""
Fitting what a shot renders to its reference picture by eye (``fit_sky.py``, ``fit_set.py``).

A frame is compared on the blocks it is fitted on (weights 1, the rest 0) as the eye tells colours apart: CIE Lab of
both pictures, each blurred over ``BLUR`` blocks within the fitted blocks (a cloud or a lamp a little off its place
is a little wrong rather than wholly), the mean distance over the blocks -- leaving out the worst ``trim`` of them,
what the fit cannot be asked to draw (a title over the picture, a fold of her coat the masks missed) -- plus how
its colours are spread (the :data:`QUANTILES` of each of L, a and b over the blocks: as bright, as blue, as much
cloud wherever it stands), the mean distance of the quantiles summed over L, a and b, times ``spread`` (a sky whose
clouds cannot stand exactly where the picture's do is drawn grey to spare them unless its spread of colours counts),
plus how much detail it has (:func:`detail`: the energy of its lightness's bands at :data:`TEXTURE_SCALES` blocks
where the band's whole reach is fitted, the absolute log of each band's ratio to the reference's summed) times
``texture`` (a sky of small torn cloudlets and one of big soft clouds blur to the same blocks).  Parameters are turned
one after another (:func:`descend`), each a step the better way and on that way while it keeps getting better (up to
:data:`REACH` steps: a step a round, the steps halving round by round, no value could move more than two of its steps
in all, and a sky a tenth too sparse stayed so).
"""
import numpy as np

BLUR = 2.0
QUANTILES = [10, 30, 50, 70, 90]
TEXTURE_SCALES = [1.0, 2.0, 4.0]
TEXTURE_REACH = 0.9
TEXTURE_FLOOR = 0.05
REACH = 8


def lab(rgb):
    """CIE Lab of display sRGB 0..255 (D65)."""
    value = rgb / 255.0
    linear = np.where(value <= 0.04045, value / 12.92, ((value + 0.055) / 1.055) ** 2.4)
    xyz = linear @ np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]).T
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6.0 / 29.0) ** 3, np.cbrt(xyz), xyz / (3.0 * (6.0 / 29.0) ** 2) + 4.0 / 29.0)
    return np.stack([116.0 * f[..., 1] - 16.0, 500.0 * (f[..., 0] - f[..., 1]), 200.0 * (f[..., 1] - f[..., 2])], axis=-1)


def blur(field, sigma):
    """``field`` (rows x columns) blurred by a Gaussian ``sigma`` blocks wide."""
    radius = int(np.ceil(sigma * 3.0))
    kernel = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2)
    rows = np.apply_along_axis(lambda line: np.convolve(line, kernel, mode="same"), 1, field)
    return np.apply_along_axis(lambda line: np.convolve(line, kernel, mode="same"), 0, rows)


def blurred(values, weight, sigma=BLUR):
    """``values`` (rows x columns x channels) blurred within ``weight``."""
    total = np.stack([blur(values[..., channel] * weight, sigma) for channel in range(values.shape[-1])], axis=-1)
    return total / np.maximum(blur(weight, sigma), 1e-6)[..., None]


def detail(lightness, weight):
    """How much detail ``lightness`` (rows x columns) has within ``weight``: for each of :data:`TEXTURE_SCALES` the mean
    size of its band between a blur that wide and one twice as wide, over the blocks whose whole reach (twice the scale)
    is at least :data:`TEXTURE_REACH` fitted."""
    energies = []
    for sigma in TEXTURE_SCALES:
        fine = blurred(lightness[..., None], weight, sigma)[..., 0]
        coarse = blurred(lightness[..., None], weight, 2.0 * sigma)[..., 0]
        counted = (weight > 0.5) & (blur(weight, 2.0 * sigma) / blur(np.ones_like(weight), 2.0 * sigma) >= TEXTURE_REACH)
        energies.append(float(np.abs(fine - coarse)[counted].mean()) if counted.any() else 0.0)
    return np.array(energies)


class Measure:
    """The reference frames to fit to: ``pictures`` {frame: blocks RGB 0..255}, ``weights`` {frame: 0/1 blocks}."""

    def __init__(self, pictures, weights, trim=0.0, spread=1.0, texture=0.0):
        self.weights = weights
        self.trim = trim
        self.spread = spread
        self.texture = texture
        self.references = {frame: blurred(lab(picture), weights[frame]) for frame, picture in pictures.items()}
        self.reference_details = {frame: detail(lab(picture)[..., 0], weights[frame]) for frame, picture in pictures.items()}

    def distance(self, frame, picture):
        weight = self.weights[frame]
        rows, columns = weight.shape
        ours = blurred(lab(picture[:rows, :columns]), weight)
        reference = self.references[frame]
        kept = weight > 0.5
        differences = np.linalg.norm(ours - reference, axis=-1)[kept]
        if self.trim > 0.0:
            differences = np.sort(differences)[:max(1, int(round(differences.size * (1.0 - self.trim))))]
        spread = np.abs(np.percentile(ours[kept], QUANTILES, axis=0) - np.percentile(reference[kept], QUANTILES, axis=0))
        score = float(differences.mean()) + self.spread * float(spread.sum(axis=1).mean())
        if self.texture > 0.0:
            ours_detail = detail(lab(picture[:rows, :columns])[..., 0], weight)
            score += self.texture * float(np.abs(np.log((ours_detail + TEXTURE_FLOOR) / (self.reference_details[frame] + TEXTURE_FLOOR))).sum())
        return score


def descend(state, parameters, score, rounds, read, changed, log):
    """Coordinate descent from ``state`` (each value raised to its lowest first): ``parameters`` [(key, step, lowest)],
    ``score(state)`` -> (value, parts), ``read(state, key)`` the value, ``changed(state, key, value)`` a new state.
    Each parameter is stepped either way and, the better way found, on that way while it keeps getting better (up to
    :data:`REACH` steps), the steps halving round by round.  Returns the best state and score."""
    for key, _step, lowest in parameters:
        if read(state, key) < lowest:
            state = changed(state, key, lowest)
    best, parts = score(state)
    log(f"start {best:.3f} {[round(part, 2) for part in parts]}")
    for round_index in range(rounds):
        for key, step, lowest in parameters:
            step = step * 0.5 ** round_index
            for direction in (-1.0, 1.0):
                moved = False
                for _ in range(REACH):
                    current = read(state, key)
                    candidate = max(current + direction * step, lowest)
                    if candidate == current:
                        break
                    trial = changed(state, key, candidate)
                    value, trial_parts = score(trial)
                    if value >= best - 1e-4:
                        break
                    best, state, parts, moved = value, trial, trial_parts, True
                    log(f"round {round_index} {key} -> {candidate:.4f}: {best:.3f} {[round(part, 2) for part in parts]}")
                if moved:
                    break
    return state, best
