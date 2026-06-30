"""Unit tests for WCAG contrast checks (pure maths, no network)."""

import pytest

from ghost_mcp.errors import GhostError
from ghost_mcp.vision.contrast import contrast_ratio, evaluate_contrast, parse_color


def test_black_on_white_is_the_maximum_ratio() -> None:
    assert round(contrast_ratio("#000000", "#ffffff"), 1) == 21.0


def test_identical_colours_have_no_contrast() -> None:
    assert contrast_ratio("#777777", "#777777") == pytest.approx(1.0)


def test_ratio_is_symmetric_regardless_of_order() -> None:
    # The ratio is defined lighter-over-darker, so swapping fg/bg is identical.
    assert contrast_ratio("#d97706", "#ffffff") == pytest.approx(
        contrast_ratio("#ffffff", "#d97706")
    )


def test_rgb_and_hex_inputs_agree() -> None:
    assert contrast_ratio("rgb(217, 119, 6)", "#ffffff") == pytest.approx(
        contrast_ratio("#d97706", "#ffffff")
    )


def test_parse_color_normalises_shorthand_and_alpha() -> None:
    assert parse_color("#FFF") == "#ffffff"
    assert parse_color("#d97706ff") == "#d97706"  # alpha dropped
    assert parse_color("rgba(217, 119, 6, 0.5)") == "#d97706"  # alpha ignored


def test_unparseable_colour_raises() -> None:
    for bad in ("rebeccapurple", "var(--accent)", "linear-gradient(red, blue)"):
        with pytest.raises(GhostError):
            parse_color(bad)


def test_evaluate_black_on_white_passes_aaa() -> None:
    result = evaluate_contrast("#000000", "#ffffff")
    assert result["ratio"] == 21.0
    assert result["AA"] == {"normal": True, "large": True}
    assert result["AAA"] == {"normal": True, "large": True}
    assert result["passes"] == "AAA"


def test_evaluate_amber_on_white_only_clears_large_text() -> None:
    # Forge amber (#d97706) on white is ~3.4:1 -- fine for large text, fails AA body.
    result = evaluate_contrast("#d97706", "#ffffff")
    assert result["AA"]["large"] is True
    assert result["AA"]["normal"] is False
    assert result["passes"] == "AA large"
    assert "large text" in result["recommendation"]


def test_evaluate_low_contrast_fails_outright() -> None:
    result = evaluate_contrast("#cccccc", "#ffffff")
    assert result["passes"] == "none"
    assert result["AA"]["large"] is False
    assert "Fails" in result["recommendation"]


def test_evaluate_white_on_forge_background_is_readable() -> None:
    # White text on the dark slate page background should clear AA for all text.
    result = evaluate_contrast("#ffffff", "#0f172a")
    assert result["AA"]["normal"] is True
