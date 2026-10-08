"""Turn a word into a sequence-logo style image."""

from __future__ import annotations

import dataclasses
import hashlib
import io
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties, findfont
from matplotlib.patches import PathPatch
from matplotlib.textpath import TextPath
from matplotlib.transforms import Affine2D

from .colors import color_for, parse_color_overrides

FORMATS = ("png", "svg", "pdf", "jpg", "jpeg", "webp")
MAX_CHARS = 64
MAX_PIXELS = 8000
_FONT_FALLBACKS = ("Arial", "Helvetica Neue", "Liberation Sans", "DejaVu Sans")

# TextPath and its glyph cache are not thread safe; the web server renders
# from several threads.
_RENDER_LOCK = threading.Lock()


@dataclass
class MotifStyle:
    """Every knob that controls how a logo looks. All fields have defaults."""

    # Canvas
    width: int = 800                 # pixels
    height: int = 400                # pixels
    dpi: int = 100
    margin: float = 0.05             # fraction of the canvas left empty on each side
    background: str = "white"        # any matplotlib color, or "transparent"

    # Letters
    font: str = "auto"               # family name, path to a .ttf/.otf, or "auto"
    font_weight: str = "bold"
    uppercase: bool = True
    letter_spacing: float = 0.04     # gap between columns, fraction of a column

    # Colors
    color_scheme: str = "classic"    # classic | nucleotide | protein | rainbow | mono
    colors: dict = field(default_factory=dict)  # per-letter overrides, e.g. {"H": "#f00"}
    mono_color: str = "#222222"

    # Column heights (fractions of the full logo height)
    min_height: float = 0.5
    max_height: float = 1.0
    heights: list | None = None      # explicit height per character, overrides the random ones

    # Secondary letter stacked under the main one (like "G" under "A")
    stack_probability: float = 0.25
    stack_min: float = 0.15
    stack_max: float = 0.4

    # Tiny "background" letters at the bottom of each column
    noise: float = 0.6               # 0 = clean, 1 = lots of residue
    noise_max_height: float = 0.045
    noise_alphabet: str = "ACGU"

    # Axes, like a real logo
    show_axis: bool = False
    axis_label: str = "bits"
    max_bits: float = 2.0

    # Post-processing (raster formats only)
    blur: float = 0.0                # Gaussian blur radius in pixels

    seed: int | None = None          # None = derived from the word, so output is reproducible

    def validate(self) -> MotifStyle:
        if not (16 <= self.width <= MAX_PIXELS and 16 <= self.height <= MAX_PIXELS):
            raise ValueError(f"width and height must be between 16 and {MAX_PIXELS} pixels")
        if not 10 <= self.dpi <= 1200:
            raise ValueError("dpi must be between 10 and 1200")
        if not 0 <= self.margin < 0.45:
            raise ValueError("margin must be in [0, 0.45)")
        if not 0 <= self.letter_spacing < 0.9:
            raise ValueError("letter_spacing must be in [0, 0.9)")
        if not 0 < self.min_height <= self.max_height <= 1:
            raise ValueError("need 0 < min_height <= max_height <= 1")
        if not 0 <= self.stack_probability <= 1:
            raise ValueError("stack_probability must be in [0, 1]")
        if not 0 <= self.stack_min <= self.stack_max <= 0.6:
            raise ValueError("need 0 <= stack_min <= stack_max <= 0.6")
        if not 0 <= self.noise <= 1:
            raise ValueError("noise must be in [0, 1]")
        if not 0 <= self.noise_max_height <= 0.2:
            raise ValueError("noise_max_height must be in [0, 0.2]")
        if self.blur < 0:
            raise ValueError("blur must be >= 0")
        if self.max_bits <= 0:
            raise ValueError("max_bits must be > 0")
        if self.heights is not None and any(not 0 <= h <= 1 for h in self.heights):
            raise ValueError("heights must be fractions in [0, 1]")
        return self

    @classmethod
    def from_mapping(cls, data: dict) -> MotifStyle:
        """Build a style from string values (query strings, CLI flags, JSON)."""
        kwargs = {}
        for f in dataclasses.fields(cls):
            if f.name not in data or data[f.name] is None:
                continue
            raw = data[f.name]
            if f.name == "seed":
                kwargs[f.name] = None if str(raw).strip() == "" else int(raw)
            elif f.name == "colors":
                kwargs[f.name] = raw if isinstance(raw, dict) else parse_color_overrides(raw)
            elif f.name == "heights":
                kwargs[f.name] = (list(map(float, raw)) if isinstance(raw, (list, tuple))
                                  else [float(x) for x in str(raw).split(",") if x.strip()]) or None
            else:
                default = f.default
                if isinstance(default, bool):
                    kwargs[f.name] = raw if isinstance(raw, bool) else str(raw).lower() in ("1", "true", "yes", "on")
                elif isinstance(default, int):
                    kwargs[f.name] = int(float(raw))
                elif isinstance(default, float):
                    kwargs[f.name] = float(raw)
                else:
                    kwargs[f.name] = str(raw)
        return cls(**kwargs)


@dataclass
class Glyph:
    char: str
    height: float   # fraction of the full logo height
    color: str


@dataclass
class Column:
    char: str
    glyphs: list[Glyph]   # bottom to top

    @property
    def height(self) -> float:
        return sum(g.height for g in self.glyphs)


def _seed_for(word: str, seed: int | None) -> int:
    if seed is not None:
        return seed
    return int.from_bytes(hashlib.sha256(word.encode()).digest()[:8], "little")


def build_columns(word: str, style: MotifStyle | None = None) -> list[Column]:
    """Decide which glyphs go in each column and how tall each one is."""
    style = (style or MotifStyle()).validate()
    if style.uppercase:
        word = word.upper()
    if not word.strip():
        raise ValueError("word must contain at least one visible character")
    if len(word) > MAX_CHARS:
        raise ValueError(f"word is limited to {MAX_CHARS} characters")

    rng = np.random.default_rng(_seed_for(word, style.seed))
    alphabet = style.noise_alphabet or "ACGU"

    def color(ch: str) -> str:
        return color_for(ch, style.color_scheme, style.colors, style.mono_color)

    columns = []
    for i, ch in enumerate(word):
        # Draw every random number even for spaces so that editing one
        # character does not reshuffle the rest of the logo.
        total = rng.uniform(style.min_height, style.max_height)
        stacked = rng.random() < style.stack_probability
        stack_frac = rng.uniform(style.stack_min, style.stack_max)
        n_noise = rng.binomial(4, style.noise)
        noise_h = rng.uniform(0.15, 1.0, size=4) * style.noise_max_height * (0.4 + 0.6 * style.noise)
        noise_ch = rng.choice(list(alphabet), size=4)
        stack_ch = rng.choice([c for c in alphabet if c != ch] or list(alphabet))

        if ch.isspace():
            columns.append(Column(ch, []))
            continue
        if style.heights is not None and i < len(style.heights):
            total = style.heights[i]

        glyphs = [Glyph(str(c), float(h), color(str(c)))
                  for c, h in zip(noise_ch[:n_noise], noise_h[:n_noise])]
        if stacked:
            glyphs.append(Glyph(str(stack_ch), total * stack_frac, color(str(stack_ch))))
        main = total - sum(g.height for g in glyphs)
        glyphs.append(Glyph(ch, max(main, total * 0.3), color(ch)))
        glyphs.sort(key=lambda g: g.height)   # logos stack the tallest letter on top
        columns.append(Column(ch, glyphs))
    return columns


@lru_cache(maxsize=16)
def _font_properties(font: str, weight: str) -> FontProperties:
    if font.lower().endswith((".ttf", ".otf", ".ttc")):
        if not Path(font).is_file():
            raise ValueError(f"font file not found: {font}")
        return FontProperties(fname=font)
    families = _FONT_FALLBACKS if font == "auto" else (font, *_FONT_FALLBACKS)
    for family in families:
        fp = FontProperties(family=family, weight=weight)
        try:
            findfont(fp, fallback_to_default=False)
            return fp
        except ValueError:
            continue
    return FontProperties(weight=weight)


@lru_cache(maxsize=512)
def _glyph_path(char: str, font: str, weight: str):
    path = TextPath((0, 0), char, size=1, prop=_font_properties(font, weight))
    if len(path.vertices) == 0:
        return None
    (x0, y0), (x1, y1) = path.vertices.min(0), path.vertices.max(0)
    if x1 - x0 <= 0 or y1 - y0 <= 0:
        return None
    return path, (x0, y0, x1 - x0, y1 - y0)


def _draw_glyph(ax, glyph: Glyph, x: float, y: float, w: float, style: MotifStyle) -> None:
    if glyph.height <= 0:
        return
    got = _glyph_path(glyph.char, style.font, style.font_weight)
    if got is None:
        return
    path, (gx, gy, gw, gh) = got
    h = glyph.height * style.max_bits
    tf = Affine2D().translate(-gx, -gy).scale(w / gw, h / gh).translate(x, y)
    ax.add_patch(PathPatch(tf.transform_path(path), facecolor=glyph.color,
                           edgecolor="none", linewidth=0))


class Motif:
    """A rendered logo. Save it, get bytes, or display it in Jupyter."""

    def __init__(self, word: str, style: MotifStyle):
        self.word = word
        self.style = style
        self.columns = build_columns(word, style)

    def figure(self) -> Figure:
        s = self.style
        # Matplotlib floors inches * dpi, so nudge up to land on the exact pixel size.
        fig = Figure(figsize=((s.width + 0.01) / s.dpi, (s.height + 0.01) / s.dpi), dpi=s.dpi)
        transparent = s.background.lower() in ("transparent", "none")
        fig.patch.set_facecolor("none" if transparent else s.background)

        left = right = bottom = top = s.margin
        if s.show_axis:
            left = max(left, 64 / s.width)
            bottom = max(bottom, 34 / s.height)
        ax = fig.add_axes((left, bottom, 1 - left - right, 1 - top - bottom))
        ax.set_facecolor("none")
        n = len(self.columns)
        ax.set_xlim(0, n)
        ax.set_ylim(0, s.max_bits)

        w = 1 - s.letter_spacing
        for i, col in enumerate(self.columns):
            y = 0.0
            for g in col.glyphs:
                _draw_glyph(ax, g, i + s.letter_spacing / 2, y, w, s)
                y += g.height * s.max_bits

        if s.show_axis:
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            ax.set_ylabel(s.axis_label)
            ax.set_xticks(np.arange(n) + 0.5, [str(i + 1) for i in range(n)])
            ax.tick_params(length=3)
        else:
            ax.set_axis_off()
        return fig

    def to_bytes(self, fmt: str = "png") -> bytes:
        fmt = fmt.lower().lstrip(".")
        if fmt not in FORMATS:
            raise ValueError(f"unsupported format {fmt!r}; choose from {FORMATS}")
        s = self.style
        transparent = s.background.lower() in ("transparent", "none")
        with _RENDER_LOCK:
            fig = self.figure()
            FigureCanvasAgg(fig)
            buf = io.BytesIO()
            raster = fmt in ("png", "jpg", "jpeg", "webp")
            fig.savefig(buf, format="png" if raster else fmt, dpi=s.dpi,
                        transparent=transparent, facecolor=fig.get_facecolor())
        data = buf.getvalue()
        if raster and (fmt != "png" or s.blur > 0):
            data = _postprocess(data, fmt, s.blur)
        return data

    def save(self, path: str | Path, fmt: str | None = None) -> Path:
        path = Path(path)
        fmt = fmt or path.suffix.lstrip(".") or "png"
        path.write_bytes(self.to_bytes(fmt))
        return path

    def to_pil(self):
        from PIL import Image
        return Image.open(io.BytesIO(self.to_bytes("png")))

    def _repr_png_(self) -> bytes:
        return self.to_bytes("png")

    def __repr__(self) -> str:
        return f"Motif({self.word!r}, {self.style.width}x{self.style.height})"


def _postprocess(png: bytes, fmt: str, blur: float) -> bytes:
    from PIL import Image, ImageFilter

    img = Image.open(io.BytesIO(png))
    if blur > 0:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    if fmt in ("jpg", "jpeg"):
        bg = Image.new("RGB", img.size, "white")
        bg.paste(img, mask=img.getchannel("A") if img.mode == "RGBA" else None)
        img = bg
    out = io.BytesIO()
    img.save(out, format={"jpg": "JPEG", "jpeg": "JPEG"}.get(fmt, fmt.upper()), quality=95)
    return out.getvalue()


def generate(word: str, style: MotifStyle | None = None, **options) -> Motif:
    """Create a logo for ``word``.

    Options can be passed as a ``MotifStyle`` or as keyword arguments, e.g.
    ``generate("Happy", width=1200, height=400, noise=0.2)``.
    """
    style = dataclasses.replace(style or MotifStyle(), **options).validate()
    return Motif(word, style)


def save(word: str, path: str | Path, **options) -> Path:
    """Shortcut for ``generate(word, **options).save(path)``."""
    return generate(word, **options).save(path)
