"""A tiny, dependency-free QR encoder: just enough of ISO/IEC 18004 to turn a short URL into a
scannable code, rendered as an inline SVG.

Byte mode only, error-correction level M, auto-selecting the smallest of versions 1-10 (up to 174
bytes) that fits the payload — plenty for a feed URL, and small enough to keep this module a few
hundred lines instead of reimplementing the whole 40-version standard. Everything here (Galois-field
arithmetic, Reed-Solomon error correction, the BCH format/version codes, module placement, masking)
follows the published algorithm directly; there is nothing swelter-specific about a QR code, so
nothing here is swelter-specific either. No PNG, no external renderer — just the matrix and an
``<svg>`` string, matching the project's no-external-runtime-dependency discipline (pyyaml is the
only one, and this isn't it).
"""

from __future__ import annotations

from collections.abc import Sequence

# -- GF(256) arithmetic (primitive polynomial 0x11D), for Reed-Solomon --------------------------

_GF_EXP = [0] * 512
_GF_LOG = [0] * 256
_x = 1
for _i in range(255):
    _GF_EXP[_i] = _x
    _GF_LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _GF_EXP[_i] = _GF_EXP[_i - 255]


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _GF_EXP[_GF_LOG[a] + _GF_LOG[b]]


def _rs_generator_poly(ecc_len: int) -> list[int]:
    """The Reed-Solomon generator polynomial of degree ``ecc_len`` (coefficients, highest first)."""
    poly = [1]
    for i in range(ecc_len):
        # multiply poly by (x - 2^i), i.e. (x + 2^i) in GF(2^8)
        next_poly = [0] * (len(poly) + 1)
        for j, coef in enumerate(poly):
            next_poly[j] ^= coef
            next_poly[j + 1] ^= _gf_mul(coef, _GF_EXP[i])
        poly = next_poly
    return poly


def _rs_encode(data: Sequence[int], ecc_len: int) -> list[int]:
    """The ``ecc_len`` Reed-Solomon error-correction codewords for ``data`` codewords."""
    generator = _rs_generator_poly(ecc_len)
    buf = list(data) + [0] * ecc_len
    for i in range(len(data)):
        coef = buf[i]
        if coef == 0:
            continue
        for j, g in enumerate(generator):
            buf[i + j] ^= _gf_mul(g, coef)
    return buf[len(data) :]


# -- BCH codes for the format (15,5) and version (18,6) info strings ----------------------------

_FORMAT_GENERATOR = 0b10100110111  # x^10+x^8+x^5+x^4+x^2+x+1
_FORMAT_MASK = 0b101010000010010
_VERSION_GENERATOR = 0b1_1111_0010_0101  # x^12+x^11+x^10+x^9+x^8+x^5+x^2+1


def _bch_remainder(value: int, generator: int) -> int:
    gen_bits = generator.bit_length()
    while value.bit_length() >= gen_bits:
        value ^= generator << (value.bit_length() - gen_bits)
    return value


def _format_bits(mask: int) -> int:
    """15-bit format string for error-correction level M (bits ``00``) and the given mask."""
    data = (0b00 << 3) | mask  # 2 bits EC level (M) + 3 bits mask pattern
    remainder = _bch_remainder(data << 10, _FORMAT_GENERATOR)
    return ((data << 10) | remainder) ^ _FORMAT_MASK


def _version_bits(version: int) -> int:
    """18-bit version string (only placed on the symbol for version >= 7)."""
    remainder = _bch_remainder(version << 12, _VERSION_GENERATOR)
    return (version << 12) | remainder


# -- Per-version capacity: (num_blocks, block_total_codewords, block_data_codewords) at level M --

_RS_BLOCKS: dict[int, list[tuple[int, int, int]]] = {
    1: [(1, 26, 16)],
    2: [(1, 44, 28)],
    3: [(1, 70, 44)],
    4: [(2, 50, 32)],
    5: [(2, 67, 43)],
    6: [(4, 43, 27)],
    7: [(4, 49, 31)],
    8: [(2, 60, 38), (2, 61, 39)],
    9: [(3, 58, 36), (2, 59, 37)],
    # Was (2, 68+18, 68), (2, 69+18, 69) — that is version 10's *Level-L* block structure (274
    # data codewords; matches the 271-byte capacity `_choose_version` used to allow). `_format_bits`
    # hard-codes the EC-level indicator to level M for every symbol this module emits, so a real
    # decoder trusts the format info, reads "level M", and de-interleaves using level-M block
    # boundaries — which never matched the level-L split actually used here, corrupting every
    # version-10 code regardless of mask (verified: all 8 mask patterns failed to decode against
    # an independent decoder before this fix; capacity/self-consistency checks never caught it
    # because encode and this module's own tests both derived from the same wrong table). The
    # correct level-M structure is 4 blocks of 43 data codewords + 1 block of 44 (216 data
    # codewords total, 213-byte capacity — the publicly documented version-10-M figure).
    10: [(4, 69, 43), (1, 70, 44)],
}

#: Alignment-pattern center coordinates per version (empty for version 1, which has none).
_ALIGNMENT: dict[int, list[int]] = {
    1: [],
    2: [6, 18],
    3: [6, 22],
    4: [6, 26],
    5: [6, 30],
    6: [6, 34],
    7: [6, 22, 38],
    8: [6, 24, 42],
    9: [6, 26, 46],
    10: [6, 28, 50],
}

#: Filler bits appended after all codeword bits, before masking, so the module count divides evenly.
_REMAINDER_BITS: dict[int, int] = {1: 0, 2: 7, 3: 7, 4: 7, 5: 7, 6: 7, 7: 0, 8: 0, 9: 0, 10: 0}

_MAX_VERSION = 10


def _data_codewords(version: int) -> int:
    return sum(n * data for n, _total, data in _RS_BLOCKS[version])


class QRTooLargeError(ValueError):
    """The payload doesn't fit in any supported version (1-10, error-correction level M)."""


def _choose_version(byte_len: int) -> int:
    for version in range(1, _MAX_VERSION + 1):
        count_bits = 8 if version <= 9 else 16
        header_bits = 4 + count_bits
        needed = header_bits + 8 * byte_len
        if needed <= _data_codewords(version) * 8:
            return version
    raise QRTooLargeError(
        f"{byte_len} bytes is too long for a QR code at error-correction level M "
        f"(max {_data_codewords(_MAX_VERSION) - 3} bytes here)"
    )


class _BitBuffer:
    def __init__(self) -> None:
        self.bits: list[int] = []

    def put(self, value: int, length: int) -> None:
        for i in range(length - 1, -1, -1):
            self.bits.append((value >> i) & 1)

    def __len__(self) -> int:
        return len(self.bits)


def _encode_codewords(data: bytes, version: int) -> list[int]:
    """Byte-mode data codewords for ``data`` at ``version``, padded to that version's capacity."""
    capacity_bits = _data_codewords(version) * 8
    buf = _BitBuffer()
    buf.put(0b0100, 4)  # byte-mode indicator
    count_bits = 8 if version <= 9 else 16
    buf.put(len(data), count_bits)
    for byte in data:
        buf.put(byte, 8)
    # Terminator: up to 4 zero bits, only as many as remain.
    buf.put(0, min(4, capacity_bits - len(buf)))
    while len(buf) % 8 != 0:
        buf.put(0, 1)
    codewords = [
        int("".join(str(b) for b in buf.bits[i : i + 8]), 2) for i in range(0, len(buf), 8)
    ]
    pad = (0xEC, 0x11)
    i = 0
    while len(codewords) < _data_codewords(version):
        codewords.append(pad[i % 2])
        i += 1
    return codewords


def _interleave(version: int, data_codewords: list[int]) -> list[int]:
    """Split data codewords into their RS blocks, add ECC per block, and interleave column-wise —
    the order a QR reader expects the codeword stream in (ISO/IEC 18004 §8.6)."""
    blocks = _RS_BLOCKS[version]
    data_groups: list[list[int]] = []
    ecc_groups: list[list[int]] = []
    pos = 0
    for count, total, data_len in blocks:
        ecc_len = total - data_len
        for _ in range(count):
            block = data_codewords[pos : pos + data_len]
            pos += data_len
            data_groups.append(block)
            ecc_groups.append(_rs_encode(block, ecc_len))
    out: list[int] = []
    for i in range(max(len(g) for g in data_groups)):
        for g in data_groups:
            if i < len(g):
                out.append(g[i])
    for i in range(max(len(g) for g in ecc_groups)):
        for g in ecc_groups:
            if i < len(g):
                out.append(g[i])
    return out


# -- Matrix construction --------------------------------------------------------------------------

_FINDER = (
    "1111111",
    "1000001",
    "1011101",
    "1011101",
    "1011101",
    "1000001",
    "1111111",
)
_ALIGN_PATTERN = ("11111", "10001", "10101", "10001", "11111")


def _new_grid(size: int) -> tuple[list[list[int]], list[list[bool]]]:
    matrix = [[0] * size for _ in range(size)]
    reserved = [[False] * size for _ in range(size)]
    return matrix, reserved


def _stamp(
    matrix: list[list[int]], reserved: list[list[bool]], top: int, left: int, pattern: Sequence[str]
) -> None:
    size = len(matrix)
    for dr, row in enumerate(pattern):
        for dc, ch in enumerate(row):
            r, c = top + dr, left + dc
            if 0 <= r < size and 0 <= c < size:
                matrix[r][c] = 1 if ch == "1" else 0
                reserved[r][c] = True


def _place_finder(matrix: list[list[int]], reserved: list[list[bool]], top: int, left: int) -> None:
    size = len(matrix)
    # Clear the finder pattern plus its one-module white separator first.
    for r in range(top - 1, top + 8):
        for c in range(left - 1, left + 8):
            if 0 <= r < size and 0 <= c < size:
                matrix[r][c] = 0
                reserved[r][c] = True
    _stamp(matrix, reserved, top, left, _FINDER)


def _place_alignment_patterns(
    matrix: list[list[int]], reserved: list[list[bool]], version: int
) -> None:
    positions = _ALIGNMENT[version]
    if not positions:
        return
    corners = {
        (positions[0], positions[0]),
        (positions[0], positions[-1]),
        (positions[-1], positions[0]),
    }
    for r in positions:
        for c in positions:
            if (r, c) in corners:
                continue
            _stamp(matrix, reserved, r - 2, c - 2, _ALIGN_PATTERN)


def _place_timing_patterns(matrix: list[list[int]], reserved: list[list[bool]]) -> None:
    size = len(matrix)
    for i in range(8, size - 8):
        bit = 1 if i % 2 == 0 else 0
        if not reserved[6][i]:
            matrix[6][i] = bit
            reserved[6][i] = True
        if not reserved[i][6]:
            matrix[i][6] = bit
            reserved[i][6] = True


def _reserve_format_areas(matrix: list[list[int]], reserved: list[list[bool]]) -> None:
    size = len(matrix)
    for i in range(9):
        if i != 6:
            reserved[8][i] = True
            reserved[i][8] = True
    for i in range(8):
        reserved[8][size - 1 - i] = True
        reserved[size - 1 - i][8] = True
    reserved[size - 8][8] = True


def _write_format_bits(matrix: list[list[int]], mask: int) -> None:
    size = len(matrix)
    bits = _format_bits(mask)
    # bit 14 (MSB) down to bit 0, split across two copies per ISO/IEC 18004 Figure 25.
    for i in range(15):
        bit = (bits >> i) & 1
        # Copy 1: around the top-left finder.
        if i < 6:
            matrix[i][8] = bit
        elif i < 8:
            matrix[i + 1][8] = bit
        elif i == 8:
            matrix[8][7] = bit
        else:
            matrix[8][14 - i] = bit
        # Copy 2: top-right column + bottom-left row.
        if i < 8:
            matrix[8][size - 1 - i] = bit
        else:
            matrix[size - 15 + i][8] = bit
    matrix[size - 8][8] = 1  # the dark module, always on


def _write_version_bits(matrix: list[list[int]], version: int) -> None:
    if version < 7:
        return
    size = len(matrix)
    bits = _version_bits(version)
    for i in range(18):
        bit = (bits >> i) & 1
        matrix[i // 3][size - 11 + i % 3] = bit
        matrix[size - 11 + i % 3][i // 3] = bit


def _place_data(matrix: list[list[int]], reserved: list[list[bool]], bits: list[int]) -> None:
    size = len(matrix)
    idx = 0
    right = size - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(size):
            for j in range(2):
                x = right - j
                upward = ((right + 1) & 2) == 0
                y = (size - 1 - vert) if upward else vert
                if not reserved[y][x]:
                    matrix[y][x] = bits[idx] if idx < len(bits) else 0
                    idx += 1
        right -= 2


def _mask_fn(pattern: int):  # type: ignore[no-untyped-def]
    return {
        0: lambda r, c: (r + c) % 2 == 0,
        1: lambda r, c: r % 2 == 0,
        2: lambda r, c: c % 3 == 0,
        3: lambda r, c: (r + c) % 3 == 0,
        4: lambda r, c: (r // 2 + c // 3) % 2 == 0,
        5: lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
        6: lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
        7: lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
    }[pattern]


def _apply_mask(
    matrix: list[list[int]], reserved: list[list[bool]], pattern: int
) -> list[list[int]]:
    fn = _mask_fn(pattern)
    size = len(matrix)
    out = [row[:] for row in matrix]
    for r in range(size):
        for c in range(size):
            if not reserved[r][c] and fn(r, c):
                out[r][c] ^= 1
    return out


def _line_penalty(line: list[int], size: int) -> int:
    """Rules 1 and 3 for a single row/column: long runs, and finder-like patterns."""
    score = 0
    run = 1
    for i in range(1, size):
        if line[i] == line[i - 1]:
            run += 1
        else:
            if run >= 5:
                score += 3 + (run - 5)
            run = 1
    if run >= 5:
        score += 3 + (run - 5)
    s = "".join(str(b) for b in line)
    for pattern in ("10111010000", "00001011101"):
        start = 0
        while True:
            found = s.find(pattern, start)
            if found == -1:
                break
            score += 40
            start = found + 1
    return score


def _penalty(matrix: list[list[int]]) -> int:
    """The four ISO/IEC 18004 §8.8.2 penalty rules, lower is better."""
    size = len(matrix)
    lines = list(matrix) + [[matrix[r][c] for r in range(size)] for c in range(size)]
    score = sum(_line_penalty(line, size) for line in lines)
    for r in range(size - 1):
        for c in range(size - 1):
            v = matrix[r][c]
            if v == matrix[r][c + 1] == matrix[r + 1][c] == matrix[r + 1][c + 1]:
                score += 3
    dark = sum(sum(row) for row in matrix)
    percent = dark * 100 // (size * size)
    score += (abs(percent - 50) // 5) * 10
    return score


def _build_matrix(data: bytes) -> list[list[int]]:
    version = _choose_version(len(data))
    codewords = _encode_codewords(data, version)
    interleaved = _interleave(version, codewords)
    bits: list[int] = []
    for cw in interleaved:
        for i in range(7, -1, -1):
            bits.append((cw >> i) & 1)
    bits.extend([0] * _REMAINDER_BITS[version])

    size = 17 + 4 * version
    matrix, reserved = _new_grid(size)
    _place_finder(matrix, reserved, 0, 0)
    _place_finder(matrix, reserved, 0, size - 7)
    _place_finder(matrix, reserved, size - 7, 0)
    _place_alignment_patterns(matrix, reserved, version)
    _place_timing_patterns(matrix, reserved)
    _reserve_format_areas(matrix, reserved)
    if version >= 7:
        for i in range(6):
            for j in range(size - 11, size - 8):
                reserved[i][j] = True
                reserved[j][i] = True
    _place_data(matrix, reserved, bits)

    best_pattern, best_matrix, best_score = 0, matrix, None
    for pattern in range(8):
        candidate = _apply_mask(matrix, reserved, pattern)
        score = _penalty(candidate)
        if best_score is None or score < best_score:
            best_pattern, best_matrix, best_score = pattern, candidate, score

    _write_format_bits(best_matrix, best_pattern)
    _write_version_bits(best_matrix, version)
    return best_matrix


def qr_svg(data: str, module_px: int = 4) -> str:
    """Render ``data`` (encoded UTF-8, byte mode) as a self-contained inline ``<svg>`` string.

    ``module_px`` is the pixel size of one QR module. A 4-module quiet zone is included, as the
    standard requires for reliable scanning. Deterministic: the same input always produces the
    same matrix and the same SVG text.
    """
    matrix = _build_matrix(data.encode("utf-8"))
    size = len(matrix)
    quiet = 4
    total = size + quiet * 2
    px = total * module_px
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {px} {px}" '
        f'width="{px}" height="{px}" shape-rendering="crispEdges" role="img" '
        f'aria-label="QR code">',
        f'<rect width="{px}" height="{px}" fill="#fff"/>',
    ]
    rects: list[str] = []
    for r in range(size):
        row = matrix[r]
        c = 0
        while c < size:
            if row[c]:
                start = c
                while c < size and row[c]:
                    c += 1
                width = c - start
                x = (start + quiet) * module_px
                y = (r + quiet) * module_px
                rects.append(
                    f'<rect x="{x}" y="{y}" width="{width * module_px}" height="{module_px}"/>'
                )
            else:
                c += 1
    parts.append(f'<g fill="#000">{"".join(rects)}</g>')
    parts.append("</svg>")
    return "".join(parts)
