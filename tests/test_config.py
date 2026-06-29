"""Unit tests for configuration parsing (no environment or network access)."""

import pytest

from ghost_mcp.config import DEFAULT_API_VERSION, Settings, _normalize_version


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("6", "v6.0"),
        ("v6", "v6.0"),
        ("v6.0", "v6.0"),
        ("V6.1", "v6.1"),
        ("", DEFAULT_API_VERSION),
        ("   ", DEFAULT_API_VERSION),
    ],
)
def test_normalize_version(raw: str, expected: str) -> None:
    assert _normalize_version(raw) == expected


def test_admin_api_base_appends_path() -> None:
    settings = Settings(admin_url="https://example.com/", staff_token="a:b")
    assert settings.admin_api_base == "https://example.com/ghost/api/admin"


def test_site_url_strips_ghost_path() -> None:
    settings = Settings(admin_url="https://example.com/ghost", staff_token="a:b")
    assert settings.site_url == "https://example.com"


def test_api_version_defaults() -> None:
    settings = Settings(admin_url="https://example.com", staff_token="a:b")
    assert settings.api_version == DEFAULT_API_VERSION


def test_repr_hides_staff_token() -> None:
    settings = Settings(admin_url="https://example.com", staff_token="id:supersecret")
    assert "supersecret" not in repr(settings)
    assert "id:" not in repr(settings)
