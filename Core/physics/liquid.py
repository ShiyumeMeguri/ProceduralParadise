"""
Core.physics.liquid -- liquid materials carried by every particle.

A particle stores its own material (``liquid:*`` attributes), so liquids of
different kinds share one FLIP grid: each cell mixes them by mass.  A preset
is plain data::

    {"density": 1000.0, "dynamic_viscosity": 0.001, "pic": 0.03,
     "friction": 0.5, "adhesion": 0.0, "wall_stick": 0.0, "yield": 0.0}

``declare_inputs`` turns a preset into group inputs, ``particle_values``
into the per-particle values (kinematic viscosity nu = mu / rho), ``store``
writes them onto points before a FLIP step and ``read`` is the field the
solver uses.  A simulation keeps only what the particles need between
frames and stores the material again every frame; where several liquids
share a grid, each particle's ``liquid_type`` picks its material
(``typed_values``); ``forget`` removes the material again.
"""
from __future__ import annotations

__all__ = ["MATERIAL", "KEYS", "ATTRIBUTE", "TYPE_ATTRIBUTE", "INPUTS", "declare_inputs", "particle_values",
           "typed_values", "store", "read", "forget"]

TYPE_ATTRIBUTE = "liquid_type"

MATERIAL = (
    ("density", "liquid:density", "kg/m^3"),
    ("kinematic_viscosity", "liquid:kinematic_viscosity", "kinematic viscosity nu = mu / rho, m^2/s"),
    ("pic", "liquid:pic", "PIC share: 0 = pure FLIP (lively, splashy), 1 = pure PIC (thick, dissipative)"),
    ("friction", "liquid:friction", "decay rate of the tangential velocity against solids, 1/s"),
    ("adhesion", "liquid:adhesion", "acceleration towards a nearby solid surface, m/s^2"),
    ("wall_stick", "liquid:wall_stick", "0 = free slip, 1 = no slip"),
    ("yield", "liquid:yield", "Bingham yield: relative speed of the layer resting on a solid lost per second, m/s^2"),
)
KEYS = tuple(key for key, _attribute, _description in MATERIAL)
ATTRIBUTE = {key: attribute for key, attribute, _description in MATERIAL}
INPUTS = (
    ("dynamic_viscosity", "Viscosity", "Pa s; water 0.001, shampoo about 5, honey about 10", 0.0, None),
    ("density", "Density", "kg/m^3", 1.0, None),
    ("pic", "PIC Ratio", "0 = pure FLIP (lively, splashy), 1 = pure PIC (thick, dissipative)", 0.0, 1.0),
    ("friction", "Solid Friction", "1/s; decay rate of the tangential velocity against solids", 0.0, None),
    ("adhesion", "Adhesion", "m/s^2; acceleration towards a nearby solid surface", 0.0, None),
    ("wall_stick", "Wall Stick", "0 = free slip (water); 1 = no slip (goo sticks to walls and is dragged along layer by layer through its viscosity)", 0.0, 1.0),
    ("yield", "Yield Strength", "m/s^2; Bingham plasticity: slow creep without enough driving force stops, goo piles up to a finite height instead of spreading into a film", 0.0, None),
)


def declare_inputs(g, panel, preset):
    """Group inputs of one liquid (a panel), defaults from the ``preset`` dict."""
    return {key: g.inp(name, default=preset[key], min=minimum, max=maximum, desc=description, panel=panel)
            for key, name, description, minimum, maximum in INPUTS}


def particle_values(g, sockets):
    return {
        "density": sockets["density"],
        "kinematic_viscosity": sockets["dynamic_viscosity"] / g.max(sockets["density"], 1e-6),
        "pic": sockets["pic"],
        "friction": sockets["friction"],
        "adhesion": sockets["adhesion"],
        "wall_stick": sockets["wall_stick"],
        "yield": sockets["yield"],
    }


def typed_values(g, values_by_type):
    """Material fields of particles of several liquids: each particle's
    ``liquid_type`` indexes ``values_by_type`` (a list of ``particle_values``)."""
    kind = g.named(TYPE_ATTRIBUTE, "INT")
    return {key: g.index_switch(kind, [values[key] for values in values_by_type], "FLOAT") for key in KEYS}


def store(g, points, values):
    missing = set(KEYS) - set(values)
    if missing:
        raise KeyError(f"liquid material lacks {sorted(missing)}")
    for key in KEYS:
        points = g.store(points, ATTRIBUTE[key], values[key])
    return points


def read(g, key):
    return g.named(ATTRIBUTE[key])


def forget(g, points):
    """``points`` without their liquid material (present or not)."""
    return g.remove_attribute(points, "liquid:*", wildcard=True)
