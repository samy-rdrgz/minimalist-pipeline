"""A QR code, pure Python: the live page's link for a phone (lib/live.py
guests). Byte mode, error correction M, the smallest version that holds the
text; the mask by the standard's penalty rules. After Nayuki's QR Code
generator (MIT), reduced to what a link needs. See NOTES.md, "Live page:
a phone"."""

# Error correction M, per version (index 0 unused): codewords per block,
# number of blocks.
_ECC_PER_BLOCK = (-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26,
                  26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28)
_BLOCKS = (-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16,
           17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49)
_FORMAT_M = 0  # the format bits' error correction level M


def _raw_modules(ver: int) -> int:
    result = (16 * ver + 128) * ver + 64
    if ver >= 2:
        n = ver // 7 + 2
        result -= (25 * n - 10) * n - 55
        if ver >= 7:
            result -= 36
    return result


def _data_codewords(ver: int) -> int:
    return _raw_modules(ver) // 8 - _ECC_PER_BLOCK[ver] * _BLOCKS[ver]


def _mul(x: int, y: int) -> int:
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _divisor(degree: int) -> list[int]:
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _mul(root, 0x02)
    return result


def _remainder(data: list[int], divisor: list[int]) -> list[int]:
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _mul(coef, factor)
    return result


def _codewords(text: bytes) -> tuple[int, list[int]]:
    """(version, its codewords with error correction, interleaved)."""
    for ver in range(1, 41):
        count_bits = 8 if ver <= 9 else 16
        if 4 + count_bits + 8 * len(text) <= _data_codewords(ver) * 8:
            break
    else:
        raise ValueError("too long for a QR code")
    bits = [0, 1, 0, 0] + [(len(text) >> i) & 1 for i in reversed(range(count_bits))]
    for b in text:
        bits += [(b >> i) & 1 for i in reversed(range(8))]
    capacity = _data_codewords(ver) * 8
    bits += [0] * min(4, capacity - len(bits))
    bits += [0] * (-len(bits) % 8)
    data = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(data) < capacity // 8:
        data.append(pad)
        pad ^= 0xEC ^ 0x11
    # Split into blocks, each with its error correction, then interleaved.
    blocks_n, ecc_len = _BLOCKS[ver], _ECC_PER_BLOCK[ver]
    raw = _raw_modules(ver) // 8
    short_n = blocks_n - raw % blocks_n
    short_len = raw // blocks_n
    divisor = _divisor(ecc_len)
    blocks, k = [], 0
    for i in range(blocks_n):
        dat = data[k:k + short_len - ecc_len + (0 if i < short_n else 1)]
        k += len(dat)
        ecc = _remainder(dat, divisor)
        if i < short_n:
            dat = dat + [0]
        blocks.append(dat + ecc)
    out = []
    for i in range(len(blocks[0])):
        for j, block in enumerate(blocks):
            if i != short_len - ecc_len or j >= short_n:
                out.append(block[i])
    return ver, out


class _Grid:
    def __init__(self, ver: int):
        self.ver = ver
        self.size = ver * 4 + 17
        self.dark = [[False] * self.size for _ in range(self.size)]
        self.fixed = [[False] * self.size for _ in range(self.size)]

    def put(self, x: int, y: int, dark: bool) -> None:
        self.dark[y][x] = dark
        self.fixed[y][x] = True

    def functions(self) -> None:
        size = self.size
        for i in range(size):
            self.put(6, i, i % 2 == 0)
            self.put(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < size and 0 <= y < size:
                        self.put(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        positions = self._alignment()
        last = len(positions) - 1
        for i, a in enumerate(positions):
            for j, b in enumerate(positions):
                if (i, j) in ((0, 0), (0, last), (last, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.put(a + dx, b + dy, max(abs(dx), abs(dy)) != 1)
        self.format(0)  # reserved now, written with the mask chosen
        if self.ver >= 7:
            rem = self.ver
            for _ in range(12):
                rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = self.ver << 12 | rem
            for i in range(18):
                bit = (bits >> i) & 1 == 1
                a, b = size - 11 + i % 3, i // 3
                self.put(a, b, bit)
                self.put(b, a, bit)

    def _alignment(self) -> list[int]:
        if self.ver == 1:
            return []
        n = self.ver // 7 + 2
        step = (self.ver * 8 + n * 3 + 5) // (n * 4 - 4) * 2
        return list(reversed([self.size - 7 - i * step for i in range(n - 1)] + [6]))

    def format(self, mask: int) -> None:
        data = _FORMAT_M << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        bit = lambda i: (bits >> i) & 1 == 1  # noqa: E731
        size = self.size
        for i in range(6):
            self.put(8, i, bit(i))
        self.put(8, 7, bit(6))
        self.put(8, 8, bit(7))
        self.put(7, 8, bit(8))
        for i in range(9, 15):
            self.put(14 - i, 8, bit(i))
        for i in range(8):
            self.put(size - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.put(8, size - 15 + i, bit(i))
        self.put(8, size - 8, True)

    def codewords(self, data: list[int]) -> None:
        i, size = 0, self.size
        right = size - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(size):
                for j in range(2):
                    x = right - j
                    y = size - 1 - vert if (right + 1) & 2 == 0 else vert
                    if not self.fixed[y][x] and i < len(data) * 8:
                        self.dark[y][x] = (data[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            right -= 2

    def mask(self, m: int) -> None:
        tests = (
            lambda x, y: (x + y) % 2 == 0,
            lambda x, y: y % 2 == 0,
            lambda x, y: x % 3 == 0,
            lambda x, y: (x + y) % 3 == 0,
            lambda x, y: (x // 3 + y // 2) % 2 == 0,
            lambda x, y: x * y % 2 + x * y % 3 == 0,
            lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
            lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
        )
        test = tests[m]
        for y in range(self.size):
            for x in range(self.size):
                if not self.fixed[y][x] and test(x, y):
                    self.dark[y][x] = not self.dark[y][x]

    def penalty(self) -> int:
        size, dark, score = self.size, self.dark, 0
        lines = [row for row in dark] + [[dark[y][x] for y in range(size)] for x in range(size)]
        for line in lines:
            run, prev = 0, None
            for v in line:
                if v == prev:
                    run += 1
                    if run == 5:
                        score += 3
                    elif run > 5:
                        score += 1
                else:
                    run, prev = 1, v
            text = "".join("1" if v else "0" for v in line)
            for pattern in ("10111010000", "00001011101"):
                start = text.find(pattern)
                while start != -1:
                    score += 40
                    start = text.find(pattern, start + 1)
        for y in range(size - 1):
            for x in range(size - 1):
                if dark[y][x] == dark[y][x + 1] == dark[y + 1][x] == dark[y + 1][x + 1]:
                    score += 3
        total = sum(sum(row) for row in dark)
        k = (abs(total * 20 - size * size * 10) + size * size - 1) // (size * size) - 1
        return score + k * 10


def qr_matrix(text: str, mask: int | None = None) -> list[list[bool]]:
    """The QR code of text: its rows of modules, True dark (no quiet zone).
    mask: forced (0-7), else the one the penalty rules prefer."""
    ver, data = _codewords(text.encode("utf-8"))
    best = None
    for m in range(8) if mask is None else (mask,):
        grid = _Grid(ver)
        grid.functions()
        grid.codewords(data)
        grid.mask(m)
        grid.format(m)
        score = grid.penalty()
        if best is None or score < best[0]:
            best = (score, grid)
    return best[1].dark


def qr_svg(text: str, border: int = 4) -> str:
    """The QR code of text as an SVG: dark modules on white, its quiet zone
    around (border modules), scaled by whatever holds it."""
    rows = qr_matrix(text)
    size = len(rows) + border * 2
    path = "".join(
        f"M{x + border},{y + border}h1v1h-1z"
        for y, row in enumerate(rows)
        for x, dark in enumerate(row)
        if dark
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" shape-rendering="crispEdges">'
        f'<rect width="{size}" height="{size}" fill="#fff"/><path d="{path}" fill="#000"/></svg>'
    )
