# Text helpers on top of framebuf: scaled 8x8 font, degree sign, alignment.
import framebuf

BLACK = 1
WHITE = 0

_gbuf = bytearray(8)
_gfb = framebuf.FrameBuffer(_gbuf, 8, 8, framebuf.MONO_VLSB)
_DEG = (0b0110, 0b1001, 0b1001, 0b0110)
_SUBST = {"²": "2", "³": "3", "µ": "u", "ä": "a", "ö": "o", "ü": "u",
          "Ä": "A", "Ö": "O", "Ü": "U", "ß": "ss", "é": "e", "è": "e"}


def clean(s):
    """Map text to what the built-in font (ASCII + our °) can render."""
    out = []
    for ch in str(s):
        if ch == "°" or 32 <= ord(ch) < 127:
            out.append(ch)
        else:
            out.append(_SUBST.get(ch, "?"))
    return "".join(out)


def _cw(ch, scale):
    return (5 if ch == "°" else 8) * scale


def width(s, scale=1):
    return sum(_cw(ch, scale) for ch in clean(s))


def fit(s, max_px, scale=1):
    s = clean(s)
    while s and width(s, scale) > max_px:
        s = s[:-1]
    return s


def text(fb, s, x, y, scale=1, c=BLACK):
    """Draw text, return the x coordinate after the last glyph."""
    for ch in clean(s):
        if ch == "°":
            for r, bits in enumerate(_DEG):
                for i in range(4):
                    if bits & (8 >> i):
                        fb.fill_rect(x + i * scale, y + r * scale, scale, scale, c)
        elif scale == 1:
            fb.text(ch, x, y, c)
        else:
            _gfb.fill(0)
            _gfb.text(ch, 0, 0, 1)
            for cx in range(8):
                col = _gbuf[cx]
                cy = 0
                while col:
                    if col & 1:
                        run = 0
                        while col & 1:
                            run += 1
                            col >>= 1
                        fb.fill_rect(x + cx * scale, y + cy * scale, scale, run * scale, c)
                        cy += run
                    else:
                        col >>= 1
                        cy += 1
        x += _cw(ch, scale)
    return x


def center(fb, s, cx, y, scale=1, c=BLACK):
    return text(fb, s, cx - width(s, scale) // 2, y, scale, c)


def right(fb, s, rx, y, scale=1, c=BLACK):
    return text(fb, s, rx - width(s, scale), y, scale, c)


def dotted_h(fb, x, y, w, c=BLACK):
    for xx in range(x, x + w, 2):
        fb.pixel(xx, y, c)


def dotted_v(fb, x, y, h, c=BLACK):
    for yy in range(y, y + h, 2):
        fb.pixel(x, yy, c)


def hatch(fb, x, y, w, h, c=BLACK):
    """Sparse 25% dither, used for "grey" areas."""
    for yy in range(y + (y & 1), y + h, 2):
        for xx in range(x + (x & 1), x + w, 2):
            fb.pixel(xx, yy, c)
