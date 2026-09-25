"""Shanhaijing modular kit.  Importing this package registers every asset
builder with :mod:`Core.gn`'s registry (``get_asset("SHJ.Furn.TeaTable")`` ...)."""
from . import materials, architecture, furniture, props, emblem  # noqa: F401
