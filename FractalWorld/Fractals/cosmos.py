"""
The starry void every FractalWorld realm floats in.

``build_world(config)`` makes the world shader: a deep gradient from the
horizon glow to a black zenith, star fields from Voronoi cells over the
sphere of directions (each layer its own cell scale, star size, density and
brightness, every star its own tint), and a nebula of fractal noise banded
about a great circle.  Camera rays may see the sky at a different strength
than the light it sheds (``camera_strength`` / ``light_strength``), the way
a photographer exposes for the stars.

``config`` (all keys required; colours linear RGB)::

    {"zenith": [r, g, b], "horizon": [r, g, b], "horizon_height": 0.2,
     "below": [r, g, b],
     "stars": [{"scale": 420, "size": 0.25, "density": 0.4, "brightness": 2,
                "warm": [r, g, b], "cool": [r, g, b]}, ...],
     "nebula": {"colors": [[r, g, b], [r, g, b]], "strength": 0.3, "scale": 1.6,
                "band_normal": [x, y, z], "band_width": 0.4},
     "camera_strength": 1.0, "light_strength": 0.3}
"""
from __future__ import annotations

from Core import shaders as S
from Core.nodes import Tree

__all__ = ["build_world"]


def _rgba(value):
    return (*value, 1.0)


def _stars(tree, direction, layer):
    cells = tree.n("ShaderNodeTexVoronoi", direction, Scale=layer["scale"], Randomness=1.0,
                   props={"voronoi_dimensions": "3D", "feature": "F1", "distance": "EUCLIDEAN"})
    chance = tree.sep(cells["Color"])
    present = tree.map_range(chance[0], 1.0 - layer["density"], 1.0 - layer["density"] + 0.001, 0.0, 1.0)
    core = tree.map_range(cells["Distance"], 0.0, layer["size"], 1.0, 0.0)
    light = tree.math("POWER", core, 3.0) * present * tree.math("POWER", chance[1], 4.0) * layer["brightness"]
    tint = S.mix_rgb(tree, chance[2], _rgba(layer["warm"]), _rgba(layer["cool"]))
    return tree.vmath("SCALE", tint, scale=light)


def build_world(config, name="FractalWorld.Cosmos"):
    world = S.new_world(name)
    tree = Tree.wrap(world.node_tree, clear=True)
    out = tree.n("ShaderNodeOutputWorld")
    direction = tree.vmath("NORMALIZE", tree.n("ShaderNodeTexCoord")["Generated"])
    _, _, height = tree.sep(direction)
    sky = S.ramp(tree, tree.map_range(height, 0.0, config["horizon_height"], 0.0, 1.0),
                 [(0.0, _rgba(config["horizon"])), (1.0, _rgba(config["zenith"]))])["Color"]
    for layer in config["stars"]:
        sky = tree.vmath("ADD", sky, _stars(tree, direction, layer))
    nebula = config["nebula"]
    cloud = S.noise(tree, direction, scale=nebula["scale"], detail=10.0, rough=0.62, distortion=0.6)["Fac"]
    wisps = tree.map_range(cloud, 0.45, 0.8, 0.0, 1.0, interp="SMOOTHSTEP")
    across = tree.vmath("DOT_PRODUCT", direction, tuple(nebula["band_normal"]))
    band = tree.math("EXPONENT", (across * across) * (-1.0 / (nebula["band_width"] ** 2)))
    hue = S.mix_rgb(tree, S.noise(tree, direction, scale=nebula["scale"] * 0.5, detail=3.0)["Fac"],
                    _rgba(nebula["colors"][0]), _rgba(nebula["colors"][1]))
    sky = tree.vmath("ADD", sky, tree.vmath("SCALE", hue, scale=wisps * band * nebula["strength"]))
    below = tree.map_range(height, 0.0, -0.02, 0.0, 1.0)
    sky = S.mix_rgb(tree, below, sky, _rgba(config["below"]))
    camera = tree.n("ShaderNodeLightPath")["Is Camera Ray"]
    strength = config["light_strength"] + (config["camera_strength"] - config["light_strength"]) * camera
    tree.link(tree.n("ShaderNodeBackground", sky, strength)["Background"], out.n.inputs["Surface"])
    tree.layout()
    return world
