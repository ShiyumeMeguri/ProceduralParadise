"""
Clouds kit (``CIN.Clouds.*``): the sky's cumulus, a volume that lights itself.

``CIN.Clouds.Deck``: the layer of sky the cumulus fill -- a box from -1 to +1 along every
axis, which its object's placement lays over the district (its location the middle of the
layer, its scale how far the layer reaches each way), filled with ``Material``, a cloud
material (:func:`cloud_material`).

:func:`cloud_material` makes the cumulus of a sky's ``clouds`` (:data:`CLOUDS` holds what a
spec leaves out).  There is cloud where a slow 3D noise -- lumps ``lump`` metres across,
squashed upright by ``stretch`` -- rises over a ``threshold`` that climbs with the height in
the deck (``climb``) and falls where a broad weather pattern, cells ``cell`` metres across,
gathers cloud (``gather``), going from none to full over ``soft``: flat on the deck's floor,
thinning out over the outer seventh of its sides, its edges eaten into billows ``billow``
metres across (``erode``), ``density`` per metre at its thickest.  A sky whose clouds were
measured on its picture (``map``: a file of the film, ``calibration/cloud_map.py``) gathers
them by its measure where it has one -- each cell's share of cloud standing in for the weather
over the cell -- and by the broad pattern beyond it.

It glows with the light it scatters, worked out in its own shading rather than by the
renderer, whose froxels -- tens of metres deep a kilometre out -- cannot hold the sunlit skin
of a cloud.  The sun (the set's SUN lamp: its direction, power and colour) reaches a point
through the cloud sampled at the ``light_steps`` towards it (shuffled sample by sample), in
three octaves of ever fainter, ever further-reaching and ever less forward light (what a cloud
scatters on many times over), seen through a phase mixing a forward lobe (``forward``) with a
share ``back_share`` of a backward one (``backward``) and scattered in the ``color`` of the
cloud; the sky fills its shade with the ``shade`` colour, from ``shade_low`` at the deck's
floor to ``shade_high`` at its top.
"""
from __future__ import annotations

import math

import bpy
import numpy as np

from Core import shaders as S
from Core.gn import GN, asset
from Core.nodes import Tree
from .. import PALETTE

CLOUDS = {"cell": 2500.0, "lump": 450.0, "stretch": 1.6, "threshold": 0.57, "climb": 0.12, "gather": 0.6, "soft": 0.06,
          "billow": 110.0, "erode": 0.6, "density": 0.04, "light_steps": [20.0, 50.0, 120.0, 300.0], "forward": 0.6,
          "backward": 0.3, "back_share": 0.3, "color": list(PALETTE["cloud"]), "shade": list(PALETTE["cloud_shade"]),
          "shade_low": 0.25, "shade_high": 0.6}
OCTAVES = 3


@asset("CIN.Clouds.Deck", "Clouds")
def deck():
    """The cloud layer of a sky: a box from -1 to +1 filled with ``Material`` (see the module notes)."""
    graph = GN("CIN.Clouds.Deck", deck.__doc__)
    material = graph.inp("Material", "MATERIAL")
    graph.result(graph.mat(graph.cube((2.0, 2.0, 2.0)), material))
    return graph


def coverage_image(name, coverage):
    """The measured ``coverage`` (a cloud map) as the image ``name``: red its cells' share of cloud, green whether the
    cell was measured; packed, so a saved film keeps it."""
    rows = np.array([[np.nan if value is None else value / 100.0 for value in row] for row in coverage["shares"]], np.float32)
    height, width = rows.shape
    pixels = np.zeros((height, width, 4), np.float32)
    pixels[..., 0] = np.nan_to_num(rows)
    pixels[..., 1] = ~np.isnan(rows)
    pixels[..., 3] = 1.0
    image = bpy.data.images.get(name)
    if image is not None:
        bpy.data.images.remove(image)
    image = bpy.data.images.new(name, width, height, alpha=True, float_buffer=True)
    image.colorspace_settings.name = "Non-Color"
    image.pixels.foreach_set(pixels.ravel())
    image.pack()
    return image


def _weather(tree: Tree, spec, x, y, coverage):
    """How much the weather gathers cloud over (``x``, ``y``): the broad pattern, or the measured share where measured."""
    weather = tree.n("ShaderNodeTexNoise", Vector=tree.vec(x, y, 0.0), Scale=1.0 / spec["cell"], Detail=1.0, Roughness=0.5,
                     props={"noise_dimensions": "2D"})["Fac"]
    if coverage is None:
        return weather
    image, box = coverage
    place = tree.vec((x - box[0]) / (box[2] - box[0]), (y - box[1]) / (box[3] - box[1]), 0.0)
    measured = tree.n("ShaderNodeTexImage", Vector=place, props={"image": image, "interpolation": "Linear", "extension": "CLIP"})["Color"]
    share, known, _ = tree.sep(measured)
    return tree.mix(known, weather, share)


def _density(tree: Tree, spec, point, coverage):
    """The share 0..1 of cloud at the world ``point`` of the deck."""
    local = tree.n("ShaderNodeVectorTransform", Vector=point,
                   props={"vector_type": "POINT", "convert_from": "WORLD", "convert_to": "OBJECT"})["Vector"]
    across, along, up = tree.sep(local)
    height = tree.clamp01((up + 1.0) * 0.5)
    x, y, z = tree.sep(point)
    weather = _weather(tree, spec, x, y, coverage)
    body = tree.n("ShaderNodeTexNoise", Vector=tree.vec(x, y, z * spec["stretch"]), Scale=1.0 / spec["lump"], Detail=2.0,
                  Roughness=0.5, props={"noise_dimensions": "3D"})["Fac"]
    threshold = spec["threshold"] + height * spec["climb"] - (weather - 0.5) * spec["gather"]
    shape = tree.map_range(body, threshold, threshold + spec["soft"], 0.0, 1.0, interp="SMOOTHSTEP")
    floor = tree.map_range(height, 0.0, 0.03, 0.0, 1.0, interp="SMOOTHSTEP")
    sides = tree.map_range(tree.max(tree.abs(across), tree.abs(along)), 0.85, 1.0, 1.0, 0.0, interp="SMOOTHSTEP")
    billows = tree.n("ShaderNodeTexNoise", Vector=point, Scale=1.0 / spec["billow"], Detail=3.0, Roughness=0.55,
                     props={"noise_dimensions": "3D"})["Fac"]
    erosion = (1.0 - billows) * spec["erode"]
    return tree.clamp01((shape * floor * sides - erosion) / tree.max(1.0 - erosion, 0.001))


def _phase(tree: Tree, cosine, g):
    """Henyey-Greenstein phase (per steradian) of the scattering angle's ``cosine``."""
    return (1.0 - g * g) / (4.0 * math.pi) / tree.math("POWER", tree.max(1.0 + g * g - 2.0 * g * cosine, 0.0001), 1.5)


def cloud_material(name, clouds, sun, measured=None):
    """The material ``name`` of the cumulus ``clouds`` (a sky's spec, :data:`CLOUDS` filling in) lit by ``sun``
    (a SUN lamp's spec: ``direction`` towards it, ``power``, ``color``), gathered by the cloud map ``measured`` (the
    content of the file its ``map`` names) where given."""
    if sun is None:
        raise ValueError(f"{name}: clouds need the set's SUN lamp to light them")
    unknown = sorted(set(clouds) - set(CLOUDS) - {"loc", "scale", "map"})
    if unknown:
        raise KeyError(f"{name}: unknown cloud keys {unknown} (known: {sorted(CLOUDS)}, loc, scale, map)")
    if ("map" in clouds) != (measured is not None):
        raise ValueError(f"{name}: a cloud map is named and handed over together")
    coverage = (coverage_image(f"{name}.Map", measured), measured["box"]) if measured is not None else None
    spec = {**CLOUDS, **clouds}
    length = math.sqrt(sum(component * component for component in sun["direction"]))
    toward = tuple(component / length for component in sun["direction"])
    sunlight = tuple(sun["power"] * channel * albedo for channel, albedo in zip(sun.get("color", (1.0, 1.0, 1.0)), spec["color"]))

    def build(tree: Tree):
        geometry = tree.n("ShaderNodeNewGeometry")
        position, incoming = geometry["Position"], geometry["Incoming"]
        sigma = spec["density"]
        jitter = tree.n("ShaderNodeTexWhiteNoise", Vector=position, props={"noise_dimensions": "3D"})["Value"]
        depth, travelled = 0.0, 0.0
        for step in spec["light_steps"]:
            depth = depth + _density(tree, spec, position + toward * (jitter * step + travelled), coverage) * step
            travelled += step
        cosine = tree.vmath("DOT_PRODUCT", incoming, tuple(-component for component in toward))
        lit = 0.0
        for octave in range(OCTAVES):
            fading = 0.5 ** octave
            phase = tree.mix(spec["back_share"], _phase(tree, cosine, spec["forward"] * fading),
                             _phase(tree, cosine, -spec["backward"] * fading))
            lit = lit + tree.math("EXPONENT", depth * (-sigma * fading)) * phase * fading
        height = tree.clamp01((tree.sep(tree.n("ShaderNodeTexCoord")["Object"])[2] + 1.0) * 0.5)
        shade = tree.vec(*spec["shade"]) * tree.mix(height, spec["shade_low"], spec["shade_high"])
        extinction = _density(tree, spec, position, coverage) * sigma
        absorbed = tree.n("ShaderNodeVolumeAbsorption", Color=(0.0, 0.0, 0.0, 1.0), Density=extinction)["Volume"]
        glow = tree.n("ShaderNodeEmission", Color=tree.vec(*sunlight) * lit + shade, Strength=extinction)["Emission"]
        return {"Volume": tree.n("ShaderNodeAddShader", absorbed, glow)["Shader"]}
    return S.material(name, build)
