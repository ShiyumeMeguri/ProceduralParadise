"""Millennium modular kit.  Importing this package registers every asset
builder with :mod:`Core.gn`'s registry (``get_asset("MIL.Furn.Desk")`` ...)."""
from . import materials, architecture, furniture, emblem, fixtures  # noqa: F401
