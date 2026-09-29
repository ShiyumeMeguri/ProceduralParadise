"""
Core.values -- how data files become socket values.

Data files write angles in degrees and may name a palette entry instead of
giving a colour; sockets take radians and RGBA.  The conversion is decided
by the socket itself -- a node-group interface item or a group node's input
socket -- so data never says which of its numbers are angles.  Each world
passes its own palette.
"""
from __future__ import annotations

import math

__all__ = ["is_angle", "is_color", "socket_value", "apply"]


def is_angle(socket):
    return getattr(socket, "subtype", "") == "ANGLE" or getattr(socket, "bl_idname", "") == "NodeSocketFloatAngle"


def is_color(socket):
    return getattr(socket, "socket_type", "") == "NodeSocketColor" or getattr(socket, "type", "") == "RGBA"


def socket_value(socket, value, palette):
    if is_angle(socket) and not isinstance(value, bool):
        return math.radians(value)
    if is_color(socket) and isinstance(value, str):
        return (*palette[value], 1.0)
    return value


def apply(graph, node, values, palette):
    """Set the inputs of the group node ``node`` (built by ``graph``) from
    data ``values`` {input name: value}; sockets passed as values are
    linked."""
    sockets = {socket.name: socket for socket in node.n.inputs}
    for name, value in values.items():
        if name not in sockets:
            raise KeyError(f"{node.n.node_tree.name}: no input '{name}'. Inputs: {list(sockets)}")
        socket = sockets[name]
        graph.assign(socket, value if hasattr(value, "s") else socket_value(socket, value, palette))
    return node
