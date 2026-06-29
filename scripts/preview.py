"""Render and serve a local preview of a Ghost theme.

Usage:
    uv run python scripts/preview.py <theme_dir>

Opens the rendered preview in your browser and serves it until you press Ctrl+C.
"""

import sys
import tempfile
import time
import webbrowser

from ghost_mcp.theme.preview import serve_preview, write_preview


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: preview.py <theme_dir>")

    out_dir = tempfile.mkdtemp(prefix="ghost-mcp-preview-")
    written = write_preview(sys.argv[1], out_dir)
    url, server = serve_preview(out_dir)

    print(f"Serving preview at {url}")
    for name, path in written.items():
        print(f"  {name}: {url}{path.name}")
    webbrowser.open(url)

    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()
        print("\nstopped.")


if __name__ == "__main__":
    main()
