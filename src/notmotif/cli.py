"""Command line interface: ``notmotif WORD`` and ``notmotif serve``."""

from __future__ import annotations

import argparse
import dataclasses
import sys

from . import __version__
from .colors import SCHEMES
from .core import FORMATS, MotifStyle, generate

_HELP = {
    "width": "image width in pixels",
    "height": "image height in pixels",
    "dpi": "resolution (affects text size of axis labels and PDF/SVG physical size)",
    "margin": "empty border, fraction of the canvas",
    "background": 'background color, or "transparent"',
    "font": 'font family or path to a .ttf/.otf file ("auto" picks Arial/Helvetica)',
    "font_weight": "font weight, e.g. bold or normal",
    "uppercase": "convert the word to uppercase",
    "letter_spacing": "gap between letters, fraction of a column",
    "color_scheme": "color scheme: " + ", ".join(SCHEMES),
    "colors": 'per-letter colors, e.g. "H=#ff0000,A=green"',
    "mono_color": "color used by the mono scheme",
    "min_height": "shortest main column, fraction of the full height",
    "max_height": "tallest main column, fraction of the full height",
    "heights": 'explicit heights per letter, e.g. "1,0.6,0.9"',
    "stack_probability": "chance a column gets a second letter stacked under it",
    "stack_min": "smallest stacked letter, fraction of its column",
    "stack_max": "largest stacked letter, fraction of its column",
    "noise": "amount of tiny residue letters, 0 to 1",
    "noise_max_height": "tallest residue letter, fraction of the full height",
    "noise_alphabet": "letters used for stacked and residue glyphs",
    "show_axis": "draw a y axis and position numbers",
    "axis_label": "y axis label",
    "max_bits": "value at the top of the y axis",
    "blur": "Gaussian blur radius in pixels (raster formats)",
    "seed": "random seed; omit for a seed derived from the word",
}


def _add_style_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("style")
    for f in dataclasses.fields(MotifStyle):
        flag = "--" + f.name.replace("_", "-")
        help_ = _HELP.get(f.name, "")
        if isinstance(f.default, bool):
            group.add_argument(flag, dest=f.name, action=argparse.BooleanOptionalAction,
                               default=None, help=help_)
        else:
            default = "" if f.default is dataclasses.MISSING else f.default
            group.add_argument(flag, dest=f.name, default=None,
                               help=f"{help_} (default: {default})" if help_ else None)


def _render(args: argparse.Namespace) -> int:
    word = " ".join(args.word)
    style = MotifStyle.from_mapping(vars(args))
    out = args.output or f"{word.strip().replace(' ', '_') or 'motif'}.{args.format or 'png'}"
    fmt = args.format or out.rsplit(".", 1)[-1].lower()
    if fmt not in FORMATS:
        fmt = "png"
    path = generate(word, style).save(out, fmt)
    print(path)
    return 0


def _serve(args: argparse.Namespace) -> int:
    from .server import serve
    serve(host=args.host, port=args.port, open_browser=not args.no_browser)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "serve":
        p = argparse.ArgumentParser(prog="notmotif serve",
                                    description="Launch the NOTMOTIF web app locally.")
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=8765)
        p.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
        return _serve(p.parse_args(argv[1:]))

    p = argparse.ArgumentParser(
        prog="notmotif",
        description="Turn a word into a sequence-logo style image. "
                    "Run `notmotif serve` to open the web app.",
    )
    p.add_argument("word", nargs="+", help="the word to draw")
    p.add_argument("-o", "--output", help="output file (default: WORD.png)")
    p.add_argument("-f", "--format", choices=FORMATS, help="output format (default: from file name)")
    p.add_argument("--version", action="version", version=f"notmotif {__version__}")
    _add_style_args(p)
    try:
        return _render(p.parse_args(argv))
    except ValueError as e:
        p.error(str(e))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
