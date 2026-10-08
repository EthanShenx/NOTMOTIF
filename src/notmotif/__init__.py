"""NOTMOTIF: turn any word into a sequence-logo style image."""

from .colors import SCHEMES, color_for
from .core import Column, Glyph, Motif, MotifStyle, build_columns, generate, save

__all__ = ["SCHEMES", "Column", "Glyph", "Motif", "MotifStyle", "build_columns",
           "color_for", "generate", "save"]
__version__ = "0.1.0"
