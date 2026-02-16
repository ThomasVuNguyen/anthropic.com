#!/usr/bin/env python3
"""Post-process a mirror so internal Anthropic links stay local."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


REDIRECT_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url={target}">
  <title>Redirect</title>
</head>
<body>
  <p>Redirecting to <a href="{target}">{target}</a>...</p>
</body>
</html>
"""


def replace_internal_links(html_text: str, host: str) -> str:
    replacements = (
        ("https://www.anthropic.com", f"/{host}"),
        ("http://www.anthropic.com", f"/{host}"),
        ("https://anthropic.com", f"/{host}"),
        ("http://anthropic.com", f"/{host}"),
        ("//www.anthropic.com", f"/{host}"),
        ("https:\\/\\/www.anthropic.com", f"\\/{host}"),
        ("http:\\/\\/www.anthropic.com", f"\\/{host}"),
        ("https:\\/\\/anthropic.com", f"\\/{host}"),
        ("http:\\/\\/anthropic.com", f"\\/{host}"),
        ("\\/\\/www.anthropic.com", f"\\/{host}"),
    )
    updated = html_text
    for old, new in replacements:
        updated = updated.replace(old, new)
    return updated


def build_domain_aliases(domain_root: Path, source_pages: list[Path], host: str) -> tuple[int, int]:
    created = 0
    replaced_files = 0
    for html_file in source_pages:
        rel = html_file.relative_to(domain_root)
        route = rel.with_suffix("")
        alias_dir = domain_root / route

        if alias_dir.exists() and alias_dir.is_file():
            alias_dir.unlink()
            replaced_files += 1
        alias_dir.mkdir(parents=True, exist_ok=True)

        index_file = alias_dir / "index.html"
        target = f"/{host}/{route.as_posix()}.html"
        index_file.write_text(REDIRECT_TEMPLATE.format(target=target), encoding="utf-8")
        created += 1
    return created, replaced_files


def build_root_route_aliases(
    mirror_root: Path, domain_root: Path, host: str, source_pages: list[Path]
) -> tuple[int, int]:
    created = 0
    skipped = 0
    for html_file in source_pages:
        rel = html_file.relative_to(domain_root)
        route = rel.with_suffix("").as_posix()
        alias_dir = mirror_root / route
        if alias_dir.exists() and alias_dir.is_file():
            skipped += 1
            continue
        alias_dir.mkdir(parents=True, exist_ok=True)
        index_file = alias_dir / "index.html"
        target = f"/{host}/{route}.html"
        index_file.write_text(REDIRECT_TEMPLATE.format(target=target), encoding="utf-8")
        created += 1
    return created, skipped


def ensure_root_assets(mirror_root: Path, domain_root: Path) -> list[str]:
    candidates = ("_next", "images", "favicon.ico", "robots.txt", "file")
    linked: list[str] = []
    for name in candidates:
        source = domain_root / name
        target = mirror_root / name
        if not source.exists() or target.exists():
            continue
        try:
            target.symlink_to(source)
            linked.append(name)
        except OSError:
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copyfile(source, target)
            linked.append(name)
    return linked


def main() -> int:
    parser = argparse.ArgumentParser(description="Localize mirrored Anthropic links.")
    parser.add_argument("--mirror-dir", default="mirror", help="Mirror root directory.")
    parser.add_argument(
        "--primary-host",
        default="www.anthropic.com",
        help="Primary mirrored host directory used for internal links.",
    )
    args = parser.parse_args()

    mirror_root = Path(args.mirror_dir).resolve()
    domain_root = mirror_root / args.primary_host
    if not domain_root.exists():
        raise SystemExit(f"Primary host directory not found: {domain_root}")

    changed_files = 0
    for html_file in mirror_root.rglob("*.html"):
        original = html_file.read_text(encoding="utf-8", errors="replace")
        updated = replace_internal_links(original, args.primary_host)
        if updated != original:
            html_file.write_text(updated, encoding="utf-8")
            changed_files += 1

    source_pages = sorted(path for path in domain_root.rglob("*.html") if path.name != "index.html")
    domain_aliases, domain_replaced = build_domain_aliases(domain_root, source_pages, args.primary_host)
    root_aliases, root_skipped = build_root_route_aliases(
        mirror_root, domain_root, args.primary_host, source_pages
    )
    linked_assets = ensure_root_assets(mirror_root, domain_root)

    print(
        f"Updated {changed_files} HTML files. "
        f"Domain aliases: {domain_aliases} (replaced files {domain_replaced}). "
        f"Root aliases: {root_aliases} (skipped {root_skipped})."
    )
    if linked_assets:
        print("Linked root assets:", ", ".join(linked_assets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
