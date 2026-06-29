"""Package a theme directory into a ZIP archive in memory.

This is the packaging step of theme creation: given a directory of theme files
(``package.json``, ``.hbs`` templates, assets), produce the ZIP bytes that the
Admin API's theme-upload endpoint expects.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path


def package_theme(source_dir: str | Path) -> bytes:
    """Package a theme directory into ZIP bytes ready for upload.

    The archive is rooted at a single top-level folder named after the source
    directory, matching the layout Ghost expects.

    Args:
        source_dir: Path to the directory containing the theme's files.

    Returns:
        The ZIP archive as bytes.

    Raises:
        FileNotFoundError: if the directory does not exist.
    """
    source = Path(source_dir)
    if not source.is_dir():
        raise FileNotFoundError(f"theme directory not found: {source}")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                arcname = Path(source.name) / path.relative_to(source)
                archive.write(path, arcname.as_posix())
    return buffer.getvalue()
