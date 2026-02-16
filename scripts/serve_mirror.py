#!/usr/bin/env python3
"""Serve the local mirror with route rewrites for extensionless pages."""

from __future__ import annotations

import argparse
import mimetypes
import posixpath
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import SplitResult, quote, unquote, urlsplit


def has_extension(url_path: str) -> bool:
    return Path(url_path).suffix != ""


class MirrorRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str, primary_host: str):
        self._root = Path(directory).resolve()
        self._primary_host = primary_host.strip("/")
        super().__init__(*args, directory=str(self._root))

    def _file_exists(self, url_path: str) -> bool:
        rel = url_path.lstrip("/")
        fs_path = (self._root / rel).resolve()
        try:
            fs_path.relative_to(self._root)
        except ValueError:
            return False
        return fs_path.is_file()

    def _normalized_path(self, raw_path: str) -> str:
        # Keep a leading slash and collapse duplicate separators.
        norm = posixpath.normpath(unquote(raw_path))
        if not norm.startswith("/"):
            norm = "/" + norm
        return norm

    def _send_redirect(self, target_path: str, query: str) -> None:
        target = quote(target_path, safe="/:@")
        if query:
            target = f"{target}?{query}"
        self.send_response(301)
        self.send_header("Location", target)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _mapped_path(self, split: SplitResult) -> tuple[str | None, bool]:
        """
        Return (mapped_path, should_redirect).
        mapped_path is a URL path relative to the mirror root.
        """
        raw_path = unquote(split.path)
        has_trailing_slash = raw_path.endswith("/") and raw_path != "/"
        path = self._normalized_path(split.path)
        primary_prefix = f"/{self._primary_host}"

        # Preserve root and obvious static asset paths.
        if path == "/" or path.startswith(("/_next/", "/images/", "/file/")):
            return None, False

        # Route root-level extensionless pages to primary host HTML files.
        if not path.startswith(primary_prefix):
            trimmed = path.rstrip("/")
            candidate_html = f"{primary_prefix}{trimmed}.html"
            if has_trailing_slash and self._file_exists(candidate_html):
                return trimmed, True
            if not has_extension(trimmed) and self._file_exists(candidate_html):
                return candidate_html, False
            return None, False

        # For primary host pages, serve the corresponding .html directly.
        trimmed = path.rstrip("/")
        candidate_html = f"{trimmed}.html"
        if has_trailing_slash and self._file_exists(candidate_html):
            return trimmed, True
        if not has_extension(trimmed) and self._file_exists(candidate_html):
            return candidate_html, False
        return None, False

    def _rewrite_request(self) -> bool:
        split = urlsplit(self.path)
        mapped, should_redirect = self._mapped_path(split)
        if not mapped:
            return False
        if should_redirect:
            self._send_redirect(mapped, split.query)
            return True
        rewritten = quote(mapped, safe="/:@")
        if split.query:
            rewritten = f"{rewritten}?{split.query}"
        self.path = rewritten
        return False

    def do_GET(self) -> None:  # noqa: N802
        if self._rewrite_request():
            return
        super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802
        if self._rewrite_request():
            return
        super().do_HEAD()

    def guess_type(self, path: str) -> str:
        # Ensure modern web types are present.
        mimetypes.add_type("text/javascript", ".js")
        mimetypes.add_type("text/javascript", ".mjs")
        mimetypes.add_type("application/wasm", ".wasm")
        return super().guess_type(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve mirror with route rewrites.")
    parser.add_argument("--bind", default="0.0.0.0", help="Bind address.")
    parser.add_argument("--port", type=int, default=1306, help="Port.")
    parser.add_argument("--root", default="mirror", help="Mirror root directory.")
    parser.add_argument(
        "--primary-host",
        default="www.anthropic.com",
        help="Primary mirrored host for root route rewrites.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f"Mirror root does not exist: {root}")

    handler_cls = partial(
        MirrorRequestHandler,
        directory=str(root),
        primary_host=args.primary_host,
    )
    server = ThreadingHTTPServer((args.bind, args.port), handler_cls)
    print(f"Serving {root} on http://{args.bind}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
