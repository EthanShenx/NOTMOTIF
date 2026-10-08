import io
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from PIL import Image

import notmotif
from notmotif.cli import main
from notmotif.core import MotifStyle, build_columns
from notmotif.server import Handler


def test_png_has_requested_size():
    img = Image.open(io.BytesIO(notmotif.generate("Happy", width=640, height=230).to_bytes("png")))
    assert img.size == (640, 230)


@pytest.mark.parametrize("fmt, magic", [("png", b"\x89PNG"), ("pdf", b"%PDF"), ("jpg", b"\xff\xd8"), ("svg", b"<?xml")])
def test_formats(fmt, magic):
    assert notmotif.generate("ACGT").to_bytes(fmt).startswith(magic)


def test_same_word_is_reproducible_and_seed_changes_it():
    a = notmotif.generate("Happy").to_bytes()
    assert a == notmotif.generate("Happy").to_bytes()
    assert a != notmotif.generate("Happy", seed=7).to_bytes()


def test_columns_follow_logo_rules():
    cols = build_columns("Hello world", MotifStyle(stack_probability=1, noise=1))
    assert [c.char for c in cols] == list("HELLO WORLD")
    assert cols[5].glyphs == []
    for c in cols:
        if c.glyphs:
            assert c.glyphs[-1].char == c.char                     # main letter on top
            assert [g.height for g in c.glyphs] == sorted(g.height for g in c.glyphs)
            assert c.height <= 1.0 + 1e-9


def test_explicit_heights_and_colors():
    cols = build_columns("AB", MotifStyle(heights=[1.0, 0.5], noise=0, stack_probability=0,
                                          colors={"A": "#123456"}))
    assert [c.height for c in cols] == pytest.approx([1.0, 0.5])
    assert cols[0].glyphs[-1].color == "#123456"


def test_from_mapping_parses_strings():
    s = MotifStyle.from_mapping({"width": "300", "show_axis": "true", "noise": "0.1",
                                 "colors": "A=red,b=#00f", "seed": "", "heights": "1,0.5"})
    assert (s.width, s.show_axis, s.noise, s.seed, s.heights) == (300, True, 0.1, None, [1.0, 0.5])
    assert s.colors == {"A": "red", "b": "#00f"}


@pytest.mark.parametrize("bad", [dict(width=5), dict(min_height=0.9, max_height=0.5), dict(noise=2),
                                 dict(color_scheme="nope")])
def test_invalid_options(bad):
    with pytest.raises(ValueError):
        notmotif.generate("X", **bad).to_bytes()


def test_cli(tmp_path):
    out = tmp_path / "x.png"
    assert main(["Happy", "-o", str(out), "--width", "300", "--height", "120", "--show-axis"]) == 0
    assert Image.open(out).size == (300, 120)


def test_server_endpoints():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_port}"
    try:
        assert b"NOTMOTIF" in urllib.request.urlopen(base + "/").read()
        meta = json.load(urllib.request.urlopen(base + "/api/meta"))
        assert "classic" in meta["schemes"]
        png = urllib.request.urlopen(base + "/api/render?word=Hi&width=200&height=100").read()
        assert Image.open(io.BytesIO(png)).size == (200, 100)
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/api/render?word=Hi&width=1")
        assert e.value.code == 400
    finally:
        httpd.shutdown()
