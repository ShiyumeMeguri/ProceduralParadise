"""
Clouds kit (``CIN.Clouds.*``): the sky's cumulus, a volume that lights itself.

``CIN.Clouds.Deck``: the layer of sky the cumulus fill -- a box from -1 to +1 along every
axis, which its object's placement lays over the district (its location the middle of the
layer, its scale how far the layer reaches each way), filled with ``Material``, a cloud
material (:func:`cloud_material`).  A deck with a ``shell`` is the hollow between two spheres
about its location instead -- the outer as far as its scale reaches, the inner ``shell`` of
that -- for a camera that turns where it stands and sees the cumulus all round it.

:func:`cloud_material` makes the cumulus of a sky's ``clouds`` (:data:`CLOUDS` holds what a
spec leaves out).  There is cloud where a slow 3D noise -- lumps ``lump`` metres across,
squashed upright by ``stretch`` -- rises over a ``threshold`` that climbs with the height in
the deck (``climb``) and falls where a broad weather pattern, cells ``cell`` metres across,
gathers cloud (``gather``), going from none to full over ``soft``: flat on the deck's floor
(a shell's inner sphere), thinning out over the outer seventh of its sides (a shell's outer
sphere ends it), its edges eaten into billows ``billow`` metres across (``erode``), ``density``
per metre at its thickest.  A sky whose clouds were measured on its picture (``map``: a file
of the film, ``calibration/cloud_map.py``) gathers them by its measure where it has one --
each cell's share of cloud standing in for the weather over the cell, a flat deck's cells
laid over the ground, a shell's by direction from its middle; the map of each stretch of the
shot blended into the next's as the film plays (an AI picture's clouds swell and drift from
second to second) -- and by the broad pattern beyond it.

It glows with the light it scatters, worked out in its own shading rather than by the
renderer, whose froxels -- tens of metres deep a kilometre out -- cannot hold the sunlit skin
of a cloud.  The sun (the set's SUN lamp: its direction, power and colour) reaches a point
through the cloud sampled at the ``light_steps`` towards it (shuffled sample by sample), in
``octaves`` octaves of ever fainter (each half the last), ever further-reaching (each ``reach`` as
deep) and ever less forward light (what a cloud scatters on many times over: three octaves each
reaching twice as deep left a thick cloud's body all but black under a side sun, its thin edges
alone lit), seen through a phase mixing a forward lobe (``forward``) with a
share ``back_share`` of a backward one (``backward``) and scattered in the ``color`` of the
cloud; the sky fills its shade with its own light -- its colour between the horizon's and the
zenith's (:data:`SKYLIGHT` of the way up), as strong as the sky shines -- the share
``shade_low`` of it at the deck's floor, ``shade_high`` at its top: under a pale haze a cloud's
underside is nearly as bright as the sky round it, under a deep blue sky it is bluer and
darker.
"""
from __future__ import annotations

import math

import bpy
import numpy as np

from Core import anim
from Core import shaders as S
from Core.gn import GN, asset
from Core.nodes import Tree
from .. import PALETTE

CLOUDS = {"cell": 2500.0, "lump": 450.0, "stretch": 1.6, "threshold": 0.57, "climb": 0.12, "gather": 0.6, "soft": 0.06,
          "billow": 110.0, "erode": 0.6, "density": 0.04, "light_steps": [20.0, 50.0, 120.0, 300.0], "forward": 0.6,
          "backward": 0.3, "back_share": 0.3, "color": list(PALETTE["cloud"]), "shade_low": 0.25, "shade_high": 0.6,
          "octaves": 6, "reach": 0.5}
SKYLIGHT = 0.6


@asset("CIN.Clouds.Deck", "Clouds")
def deck():
    """The cloud layer of a sky: a box from -1 to +1 filled with ``Material`` (see the module notes)."""
    graph = GN("CIN.Clouds.Deck", deck.__doc__)
    material = graph.inp("Material", "MATERIAL")
    graph.result(graph.mat(graph.cube((2.0, 2.0, 2.0)), material))
    return graph


def coverage_image(name, coverage):
    """The measured ``coverage`` (a cloud map: a map a stretch of the shot) as the image ``name``: the maps one above
    another, each a row taller at either end (its edge again: a map's edge is not blended with the next map's), red a
    cell's share of cloud, green whether the cell was measured; packed, so a saved film keeps it."""
    maps = [np.array([[np.nan if value is None else value / 100.0 for value in row] for row in shares], np.float32)
            for shares in coverage["shares"]]
    stacked = np.concatenate([np.concatenate([measured[:1], measured, measured[-1:]]) for measured in maps])
    height, width = stacked.shape
    pixels = np.zeros((height, width, 4), np.float32)
    pixels[..., 0] = np.nan_to_num(stacked)
    pixels[..., 1] = ~np.isnan(stacked)
    pixels[..., 3] = 1.0
    image = bpy.data.images.get(name)
    if image is not None:
        bpy.data.images.remove(image)
    image = bpy.data.images.new(name, width, height, alpha=True, float_buffer=True)
    image.colorspace_settings.name = "Non-Color"
    image.pixels.foreach_set(pixels.ravel())
    image.pack()
    return image


def _weather(tree: Tree, spec, x, y, coverage, direction):
    """How much the weather gathers cloud over (``x``, ``y``): the broad pattern, or the measured share where measured
    (a shell's map read by the ``direction`` from its middle), the maps of the two stretches the ``frame`` lies between
    blended."""
    weather = tree.n("ShaderNodeTexNoise", Vector=tree.vec(x, y, 0.0), Scale=1.0 / spec["cell"], Detail=1.0, Roughness=0.5,
                     props={"noise_dimensions": "2D"})["Fac"]
    if coverage is None:
        return weather
    image, box, times, rows, frame = coverage
    if direction is not None:
        east, north, up = tree.sep(direction)
        x = tree.math("ARCTAN2", north, east) * (180.0 / math.pi)
        y = tree.math("ARCSINE", tree.math("MAXIMUM", tree.math("MINIMUM", up, 1.0), -1.0)) * (180.0 / math.pi)
    across, upward = (x - box[0]) / (box[2] - box[0]), (y - box[1]) / (box[3] - box[1])
    count, band = len(times), rows + 2

    def read(stretch):
        upward_in_band = (stretch * float(band) + 1.0 + upward * float(rows)) * (1.0 / (count * band))
        return tree.n("ShaderNodeTexImage", Vector=tree.vec(across, upward_in_band, 0.0),
                      props={"image": image, "interpolation": "Linear", "extension": "CLIP"})["Color"]
    if count == 1:
        measured = read(0.0)
    else:
        along = tree.min(tree.max((frame - times[0]) * ((count - 1) / (times[-1] - times[0])), 0.0), count - 1.0)
        stretch = tree.min(tree.floor(along), count - 2.0)
        measured = tree.mix(along - stretch, read(stretch), read(stretch + 1.0), "RGBA")
    share, known, _ = tree.sep(measured)
    return tree.mix(known, weather, share)


def _height(tree: Tree, spec, local):
    """How far up the deck the object-space point ``local`` stands, 0 its floor to 1 its top (a shell's inner sphere to
    its outer)."""
    if "shell" in spec:
        return tree.clamp01((tree.vmath("LENGTH", local) - spec["shell"]) / (1.0 - spec["shell"]))
    return tree.clamp01((tree.sep(local)[2] + 1.0) * 0.5)


def _density(tree: Tree, spec, point, coverage):
    """The share 0..1 of cloud at the world ``point`` of the deck."""
    local = tree.n("ShaderNodeVectorTransform", Vector=point,
                   props={"vector_type": "POINT", "convert_from": "WORLD", "convert_to": "OBJECT"})["Vector"]
    across, along, up = tree.sep(local)
    height = _height(tree, spec, local)
    x, y, z = tree.sep(point)
    shell = "shell" in spec
    weather = _weather(tree, spec, x, y, coverage, tree.vmath("NORMALIZE", local) if shell else None)
    body = tree.n("ShaderNodeTexNoise", Vector=tree.vec(x, y, z * spec["stretch"]), Scale=1.0 / spec["lump"], Detail=2.0,
                  Roughness=0.5, props={"noise_dimensions": "3D"})["Fac"]
    threshold = spec["threshold"] + height * spec["climb"] - (weather - 0.5) * spec["gather"]
    shape = tree.map_range(body, threshold, threshold + spec["soft"], 0.0, 1.0, interp="SMOOTHSTEP")
    floor = tree.map_range(height, 0.0, 0.03, 0.0, 1.0, interp="SMOOTHSTEP")
    if shell:
        sides = tree.map_range(tree.vmath("LENGTH", local), 0.97, 1.0, 1.0, 0.0, interp="SMOOTHSTEP")
    else:
        sides = tree.map_range(tree.max(tree.abs(across), tree.abs(along)), 0.85, 1.0, 1.0, 0.0, interp="SMOOTHSTEP")
    billows = tree.n("ShaderNodeTexNoise", Vector=point, Scale=1.0 / spec["billow"], Detail=3.0, Roughness=0.55,
                     props={"noise_dimensions": "3D"})["Fac"]
    erosion = (1.0 - billows) * spec["erode"]
    return tree.clamp01((shape * floor * sides - erosion) / tree.max(1.0 - erosion, 0.001))


def _phase(tree: Tree, cosine, g):
    """Henyey-Greenstein phase (per steradian) of the scattering angle's ``cosine``."""
    return (1.0 - g * g) / (4.0 * math.pi) / tree.math("POWER", tree.max(1.0 + g * g - 2.0 * g * cosine, 0.0001), 1.5)


def skylight(sky):
    """The light a sky spec (``zenith``, ``horizon``, ``strength``) sheds on its clouds' shade."""
    return [(horizon + (zenith - horizon) * SKYLIGHT) * sky.get("strength", 1.0) for horizon, zenith in zip(sky["horizon"], sky["zenith"])]


def cloud_material(name, clouds, sun, sky, measured=None):
    """The material ``name`` of the cumulus ``clouds`` (a sky's spec, :data:`CLOUDS` filling in) lit by ``sun``
    (a SUN lamp's spec: ``direction`` towards it, ``power``, ``color``) and in their shade by the ``sky`` they are
    part of (:func:`skylight`), gathered by the cloud map ``measured`` (the content of the file its ``map`` names)
    where given."""
    if sun is None:
        raise ValueError(f"{name}: clouds need the set's SUN lamp to light them")
    unknown = sorted(set(clouds) - set(CLOUDS) - {"loc", "scale", "map", "shell"})
    if unknown:
        raise KeyError(f"{name}: unknown cloud keys {unknown} (known: {sorted(CLOUDS)}, loc, scale, map, shell)")
    if ("map" in clouds) != (measured is not None):
        raise ValueError(f"{name}: a cloud map is named and handed over together")
    if measured is not None and ("shell" in clouds) != ("centre" in measured):
        raise ValueError(f"{name}: a shell's map is read by direction (a map with a centre), a flat deck's over the ground")
    if measured is not None and (len(measured["times"]) != len(measured["shares"]) or len({len(shares) for shares in measured["shares"]}) != 1):
        raise ValueError(f"{name}: a cloud map has a map of the same cells for each of its times")
    spec = {**CLOUDS, **clouds}
    length = math.sqrt(sum(component * component for component in sun["direction"]))
    toward = tuple(component / length for component in sun["direction"])
    sunlight = tuple(sun["power"] * channel * albedo for channel, albedo in zip(sun.get("color", (1.0, 1.0, 1.0)), spec["color"]))

    def build(tree: Tree):
        coverage = None
        if measured is not None:
            clock = tree.n("ShaderNodeValue")
            anim.key_seconds(clock.n.outputs[0], "default_value", clock.n.outputs[0].id_data, 1.0)
            coverage = (coverage_image(f"{name}.Map", measured), measured["box"], measured["times"], len(measured["shares"][0]), clock.o)
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
        for octave in range(int(spec["octaves"])):
            fading = 0.5 ** octave
            phase = tree.mix(spec["back_share"], _phase(tree, cosine, spec["forward"] * fading),
                             _phase(tree, cosine, -spec["backward"] * fading))
            lit = lit + tree.math("EXPONENT", depth * (-sigma * spec["reach"] ** octave)) * phase * fading
        height = _height(tree, spec, tree.n("ShaderNodeTexCoord")["Object"])
        shade = tree.vec(*skylight(sky)) * tree.mix(height, spec["shade_low"], spec["shade_high"])
        extinction = _density(tree, spec, position, coverage) * sigma
        absorbed = tree.n("ShaderNodeVolumeAbsorption", Color=(0.0, 0.0, 0.0, 1.0), Density=extinction)["Volume"]
        glow = tree.n("ShaderNodeEmission", Color=tree.vec(*sunlight) * lit + shade, Strength=extinction)["Emission"]
        return {"Volume": tree.n("ShaderNodeAddShader", absorbed, glow)["Shader"]}
    return S.material(name, build)
