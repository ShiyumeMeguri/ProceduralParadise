"""
How scene data becomes socket values: :mod:`Core.values` with the realm's
palette (angles are written in degrees).
"""
from __future__ import annotations

from Core import values as V
from . import PALETTE

__all__ = ["socket_value"]


def socket_value(socket, value):
    return V.socket_value(socket, value, PALETTE)
