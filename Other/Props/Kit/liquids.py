"""
The props' liquids as group inputs: the presets of ``Props.json`` become a
``Liquid`` menu (which one is poured from now on), a panel of material values
per liquid and the library material each renders with.  Particles carry the
index of their liquid (``liquid_type``), so poured liquids keep their kind
and mix on one grid; ``dress`` gives each face of a mixed surface the
material of its nearest particle.
"""
from __future__ import annotations

from Core.physics import liquid
from .. import LIQUIDS
from . import materials as M

NAMES = tuple(LIQUIDS)


def choice(graph, panel):
    """The ``Liquid`` menu; returns the index of the chosen liquid."""
    menu = graph.inp("Liquid", "MENU", desc="The liquid poured from now on; what has been poured keeps its kind and different liquids mix",
                     panel=panel)
    return graph.menu_switch(menu, NAMES)


def presets(graph, look_panel):
    """A closed panel of material values per liquid and one material input
    each; returns (material fields by particle, materials in NAMES order)."""
    values = [liquid.particle_values(graph, liquid.declare_inputs(graph, name, LIQUIDS[name])) for name in NAMES]
    materials = [graph.inp(f"{name} Material", "MATERIAL", default=M.get(LIQUIDS[name]["material"]), panel=look_panel) for name in NAMES]
    return liquid.typed_values(graph, values), materials


def dress(graph, surface, particles, nearest, materials):
    """``surface`` meshed from ``particles`` (``nearest``: the index of each
    vertex's nearest particle) with every face in its liquid's material."""
    kind = graph.sample_index(particles, graph.named(liquid.TYPE_ATTRIBUTE, "INT"), nearest, "INT")
    surface = graph.store(surface, liquid.TYPE_ATTRIBUTE, kind, "INT")
    face_kind = graph.math("ROUND", graph.on_domain(graph.named(liquid.TYPE_ATTRIBUTE, "INT"), "FACE"))
    for index, material in enumerate(materials):
        surface = graph.mat(surface, material, sel=graph.compare(face_kind, float(index), "EQUAL"))
    return surface
