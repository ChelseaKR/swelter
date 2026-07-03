"""The pure-Python QR encoder: deterministic output, valid structure, and a real round trip
against the reference matrix a card's SVG is built from."""

from __future__ import annotations

import re

from swelter import qr


def test_qr_svg_is_deterministic() -> None:
    a = qr.qr_svg("https://example.org/feed")
    b = qr.qr_svg("https://example.org/feed")
    assert a == b


def test_qr_svg_is_self_contained() -> None:
    svg = qr.qr_svg("https://example.org/feed")
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg


def test_different_data_gives_different_output() -> None:
    a = qr.qr_svg("https://example.org/feed?area=1")
    b = qr.qr_svg("https://example.org/feed?area=2")
    assert a != b


def test_module_px_scales_the_svg_size() -> None:
    small = qr.qr_svg("hi", module_px=2)
    big = qr.qr_svg("hi", module_px=8)

    def _dim(svg: str) -> int:
        m = re.search(r'width="(\d+)"', svg)
        assert m is not None
        return int(m.group(1))

    assert _dim(big) == _dim(small) * 4


def test_too_long_a_payload_raises() -> None:
    import pytest

    with pytest.raises(qr.QRTooLargeError):
        qr.qr_svg("x" * 500)


def test_matrix_is_valid_qr_structure() -> None:
    # Finder patterns occupy the three 7x7 corners; the center module of each must be dark, and
    # the ring immediately around it light — the classic finder signature every QR reader looks
    # for first.
    matrix = qr._build_matrix(b"https://example.org/feed")
    size = len(matrix)
    for top, left in ((0, 0), (0, size - 7), (size - 7, 0)):
        assert matrix[top + 3][left + 3] == 1  # finder center
        assert matrix[top + 1][left + 1] == 0  # inside the white ring
    # The mandatory dark module.
    assert matrix[size - 8][8] == 1


def test_svg_raster_matches_the_source_matrix() -> None:
    """The rectangles drawn in the SVG reconstruct exactly the module matrix that produced them —
    guards the row-run-length drawing logic against an off-by-one."""
    data = "https://example.org/feed"
    module_px = 4
    svg = qr.qr_svg(data, module_px=module_px)
    matrix = qr._build_matrix(data.encode("utf-8"))
    size = len(matrix)
    quiet = 4

    rects = re.findall(r'<rect x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)"/>', svg)
    grid = [[0] * size for _ in range(size)]
    for x, y, w, h in rects:
        x, y, w, h = int(x), int(y), int(w), int(h)
        col0 = x // module_px - quiet
        row = y // module_px - quiet
        for k in range(w // module_px):
            grid[row][col0 + k] = 1
    assert grid == matrix
