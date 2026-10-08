"""Color schemes for NOTMOTIF logos."""

from __future__ import annotations

# The four canonical nucleotide colors used by WebLogo/JASPAR-style logos,
# tuned to match the slightly softened tones of typical published figures.
GREEN = "#5CC83E"
BLUE = "#0A00C2"
ORANGE = "#F5B23C"
RED = "#BF2A1F"
NUCLEOTIDE = (GREEN, BLUE, ORANGE, RED)

# Every Latin letter is mapped onto one of the four nucleotide colors so that
# arbitrary words keep the classic four-color look. A, C, G, T and U keep
# their real nucleotide colors.
_CLASSIC_GROUPS = {
    GREEN: "AEIVYMO",
    BLUE: "CBHKNQW",
    ORANGE: "GDLRXS",
    RED: "TUFJPZ",
}

# WebLogo "chemistry" coloring for amino acids.
_PROTEIN_GROUPS = {
    "#109648": "GSTYC",   # polar
    "#5E239D": "NQ",      # neutral
    "#255C99": "KRH",     # basic
    "#D62839": "DE",      # acidic
    "#221E22": "AVLIPWFM",  # hydrophobic
}

_RAINBOW = [
    "#E6194B", "#F58231", "#FFC20A", "#3CB44B", "#42D4F4",
    "#4363D8", "#911EB4", "#F032E6",
]


def _expand(groups: dict[str, str]) -> dict[str, str]:
    return {ch: color for color, letters in groups.items() for ch in letters}


SCHEMES: dict[str, dict[str, str]] = {
    "classic": _expand(_CLASSIC_GROUPS),
    "nucleotide": {"A": GREEN, "C": BLUE, "G": ORANGE, "T": RED, "U": RED},
    "protein": _expand(_PROTEIN_GROUPS),
    "rainbow": {chr(65 + i): _RAINBOW[i % len(_RAINBOW)] for i in range(26)},
    "mono": {},
}

SCHEME_DESCRIPTIONS = {
    "classic": "Four nucleotide colors spread across the whole alphabet",
    "nucleotide": "Strict A/C/G/T/U colors; other characters cycle through them",
    "protein": "WebLogo amino-acid chemistry colors",
    "rainbow": "One hue per letter",
    "mono": "Single color (set with mono_color)",
}


def color_for(char: str, scheme: str, overrides: dict[str, str] | None = None,
              mono_color: str = "#222222") -> str:
    """Return the fill color for ``char`` under ``scheme``.

    ``overrides`` (keyed by character, case-insensitive) always wins.
    """
    if scheme not in SCHEMES:
        raise ValueError(f"unknown color scheme {scheme!r}; choose from {sorted(SCHEMES)}")
    key = char.upper()
    if overrides:
        for k in (char, key):
            if k in overrides:
                return overrides[k]
    if scheme == "mono":
        return mono_color
    table = SCHEMES[scheme]
    if key in table:
        return table[key]
    if scheme == "protein":
        return "#8C8C8C"
    if scheme == "rainbow":
        return _RAINBOW[ord(key) % len(_RAINBOW)]
    return NUCLEOTIDE[ord(key) % 4]


def parse_color_overrides(text: str | None) -> dict[str, str]:
    """Parse ``"H=#ff0000,A=green"`` into ``{"H": "#ff0000", "A": "green"}``."""
    if not text:
        return {}
    out: dict[str, str] = {}
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"bad color override {item!r}; expected LETTER=COLOR")
        k, v = item.split("=", 1)
        k, v = k.strip(), v.strip()
        if len(k) != 1 or not v:
            raise ValueError(f"bad color override {item!r}; expected LETTER=COLOR")
        out[k] = v
    return out
