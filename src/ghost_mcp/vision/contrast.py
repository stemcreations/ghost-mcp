"""WCAG contrast checks over brand colours (pure, no network).

The styling tools choose an accent plus text/background colours; this computes the
WCAG 2.x contrast ratio between two colours and the AA/AAA pass levels, so a
generated theme doesn't ship unreadable text-on-accent. Colours may be given as
hex (``#rgb`` / ``#rrggbb``, with or without alpha -- alpha is ignored) or as
``rgb()`` / ``rgba()``; ``var()``, gradients, and named colours are rejected.

The maths is the WCAG definition: linearise each sRGB channel, take the relative
luminance, then ``(lighter + 0.05) / (darker + 0.05)`` for a ratio in ``1.0..21.0``.
"""

from __future__ import annotations

from ghost_mcp.errors import GhostError
from ghost_mcp.vision.structure import _normalize_hex, _rgb_to_hex

#: WCAG 2.x minimum contrast ratios for AA/AAA at normal and large text sizes.
_AA_NORMAL = 4.5
_AA_LARGE = 3.0
_AAA_NORMAL = 7.0
_AAA_LARGE = 4.5


def parse_color(value: str) -> str:
    """Coerce a hex or ``rgb()``/``rgba()`` colour string to ``#rrggbb``.

    Raises ``GhostError`` on anything unparseable (named colours, gradients,
    ``var(...)``) so a bad colour fails loudly instead of scoring as black.
    """
    text = value.strip()
    if text.lower().startswith("rgb") and "(" in text and ")" in text:
        hexed = _rgb_to_hex(text[text.find("(") + 1 : text.rfind(")")])
    else:
        hexed = _normalize_hex(text)
    if hexed is None:
        raise GhostError(f"can't parse colour {value!r}; use hex (#rrggbb) or rgb()/rgba().")
    return hexed


def _channel_luminance(channel: float) -> float:
    """Linearise one sRGB channel (0..1) per the WCAG transfer function."""
    return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance of an ``#rrggbb`` colour (0 = black, 1 = white)."""
    r = int(hex_color[1:3], 16) / 255
    g = int(hex_color[3:5], 16) / 255
    b = int(hex_color[5:7], 16) / 255
    return (
        0.2126 * _channel_luminance(r)
        + 0.7152 * _channel_luminance(g)
        + 0.0722 * _channel_luminance(b)
    )


def contrast_ratio(foreground: str, background: str) -> float:
    """The WCAG contrast ratio (1.0..21.0) between two colours (hex or rgb())."""
    fg = relative_luminance(parse_color(foreground))
    bg = relative_luminance(parse_color(background))
    lighter, darker = max(fg, bg), min(fg, bg)
    return (lighter + 0.05) / (darker + 0.05)


def _recommend(passes: str, ratio: float) -> str:
    """A one-line, human-readable verdict for the highest level cleared."""
    if passes == "none":
        return (
            f"Fails WCAG AA (ratio {ratio}; needs 4.5 for normal text, 3.0 for large). "
            "Darken or lighten one colour."
        )
    if passes == "AA large":
        return (
            f"Passes AA only for large text (>=18pt, or 14pt bold) at {ratio}. "
            "Use for headings/buttons, not body copy."
        )
    if passes == "AA":
        return f"Passes AA for all text sizes at {ratio}. Meets the common accessibility bar."
    return f"Passes AAA at {ratio} -- strong contrast for all text sizes."


def evaluate_contrast(foreground: str, background: str) -> dict:
    """Contrast ratio plus WCAG AA/AAA pass levels for normal and large text.

    Args:
        foreground: The text/foreground colour (hex or ``rgb()``).
        background: The colour behind it (hex or ``rgb()``).

    Returns:
        A mapping with the normalised ``foreground``/``background``, the ``ratio``
        (rounded to 2 dp), ``AA``/``AAA`` flags for ``normal`` and ``large`` text,
        the highest level cleared (``passes``), and a ``recommendation``.
    """
    fg = parse_color(foreground)
    bg = parse_color(background)
    ratio = contrast_ratio(fg, bg)
    rounded = round(ratio, 2)
    aa = {"normal": ratio >= _AA_NORMAL, "large": ratio >= _AA_LARGE}
    aaa = {"normal": ratio >= _AAA_NORMAL, "large": ratio >= _AAA_LARGE}
    if aaa["normal"]:
        passes = "AAA"
    elif aa["normal"]:
        passes = "AA"
    elif aa["large"]:
        passes = "AA large"
    else:
        passes = "none"
    return {
        "foreground": fg,
        "background": bg,
        "ratio": rounded,
        "AA": aa,
        "AAA": aaa,
        "passes": passes,
        "recommendation": _recommend(passes, rounded),
    }
