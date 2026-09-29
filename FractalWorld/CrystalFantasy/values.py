"""
How realm and scene data become socket values: :mod:`Core.values` with the
realm's palette.
"""
from __future__ import annotations

from Core import values as V
from . import PALETTE

__all__ = ["socket_value", "apply"]


def socket_value(socket, value):
    return V.socket_value(socket, value, PALETTE)


def apply(graph, node, values):
    return V.apply(graph, node, values, PALETTE)
