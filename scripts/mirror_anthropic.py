#!/usr/bin/env python3
"""Build a high-fidelity local mirror of anthropic.com."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0 Safari/537.36 anthropic-mirror/1.0"
)

ASSET_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".css",
    ".csv",
    ".eot",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".m3u8",
    ".map",
    ".mjs",
    ".mp3",
    ".mp4",
    ".otf",
    ".pdf",
    ".png",
    ".svg",
    ".ttf",
    ".txt",
    ".wav",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".xml",
    ".zip",
}

NON_HTML_EXTENSIONS = ASSET_EXTENSIONS | {
    ".7z",
    ".bz2",
    ".doc",
    ".docx",
    ".epub",
    ".gz",
    ".ppt",
    ".pptx",
    ".rar",
    ".tar",
    ".xls",
    ".xlsx",
    ".xz",
}

TRACKING_QUERY_KEYS = {
    "utm_campaign",
    "utm_content",
    "utm_id",
    "utm_medium",
    "utm_source",
    "utm_term",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
}

IGNORE_EXTERNAL_HOST_SUFFIXES = (
    "twitter.com",
    "x.com",
    "linkedin.com",
    "youtube.com",
    "discord.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
)

CSS_URL_RE = re.compile(r"url\(([^)]+)\)", re.IGNORECASE)
ABSOLUTE_URL_RE = re.compile(r"https?://[^\s\"'<>)]+", re.IGNORECASE)


class LinkExtractor(HTMLParser):
    """Extracts URL-like values from HTML attributes, style blocks, and scripts."""

    URL_ATTRS = {
        "href",
        "src",
        "srcset",
        "poster",
        "data",
        "action",
        "imagesrcset",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: set[str] = set()
        self._in_style = False
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.lower()
        if tag_name == "style":
            self._in_style = True
        if tag_name == "script":
            self._in_script = True

        for name, value in attrs:
            if not value:
                continue
            key = name.lower()
            if key == "style":
                self.urls.update(extract_urls_from_css(value))
                continue
            if key == "content" and tag_name == "meta":
                refresh_match = re.search(r"url=([^;]+)", value, re.IGNORECASE)
                if refresh_match:
                    self.urls.add(refresh_match.group(1).strip())
                elif looks_like_url_candidate(value):
                    self.urls.add(value)
                continue
            if key not in self.URL_ATTRS:
                continue

            if key in {"srcset", "imagesrcset"}:
                for candidate in value.split(","):
                    first = candidate.strip().split()[0] if candidate.strip() else ""
                    if first:
                        self.urls.add(first)
                continue

            self.urls.add(value)

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()
        if tag_name == "style":
            self._in_style = False
        if tag_name == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.urls.update(extract_urls_from_css(data))
        if self._in_script:
            self.urls.update(ABSOLUTE_URL_RE.findall(data))


def extract_urls_from_css(text: str) -> set[str]:
    urls: set[str] = set()
    for match in CSS_URL_RE.findall(text):
        candidate = match.strip().strip("\"'")
        if candidate:
            urls.add(candidate)
    return urls


def looks_like_url_candidate(value: str) -> bool:
    candidate = value.strip().strip("\"'")
    if not candidate:
        return False
    lower = candidate.lower()
    return lower.startswith(("http://", "https://", "//", "/", "./", "../", "?"))


def normalize_url(raw_url: str, *, drop_tracking: bool = True) -> str | None:
    candidate = raw_url.strip().strip("\"'")
    if not candidate:
        return None
    if candidate.startswith("//"):
        candidate = f"https:{candidate}"
    lower = candidate.lower()
    if lower.startswith(("javascript:", "mailto:", "tel:", "data:", "about:")):
        return None

    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        return None

    host = (parsed.hostname or "").lower()
    if not host:
        return None

    if parsed.port:
        is_default = (parsed.scheme == "http" and parsed.port == 80) or (
            parsed.scheme == "https" and parsed.port == 443
        )
        netloc = host if is_default else f"{host}:{parsed.port}"
    else:
        netloc = host

    path = parsed.path or "/"
    query = parsed.query
    if drop_tracking and query:
        pairs = parse_qsl(query, keep_blank_values=True)
        pairs = [(k, v) for k, v in pairs if k.lower() not in TRACKING_QUERY_KEYS]
        query = urlencode(pairs, doseq=True)

    normalized = urlunparse((parsed.scheme, netloc, path, "", query, ""))
    return normalized


def is_internal(url: str, domain_suffix: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    normalized_suffix = domain_suffix.lower()
    return host == normalized_suffix or host.endswith(f".{normalized_suffix}")


def extension_of(url: str) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    return suffix


def likely_html(url: str) -> bool:
    path = urlparse(url).path.lower()
    if path.startswith("/api/") or "/api/" in path:
        return False
    if path.startswith("/cdn-cgi/"):
        return False
    suffix = extension_of(url)
    if not suffix:
        return True
    return suffix not in NON_HTML_EXTENSIONS


def likely_asset(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    suffix = extension_of(url)
    if suffix in ASSET_EXTENSIONS:
        return True
    if any(host == ignored or host.endswith(f".{ignored}") for ignored in IGNORE_EXTERNAL_HOST_SUFFIXES):
        return False

    parsed = urlparse(url)
    path_lower = parsed.path.lower()
    query_lower = parsed.query.lower()
    if any(token in path_lower for token in ("/_next/", "/static/", "/assets/", "/cdn/")):
        return True
    if "fonts.googleapis.com" in host or "fonts.gstatic.com" in host:
        return True
    if ".css" in query_lower or ".js" in query_lower:
        return True
    return False


def fetch_url(url: str, *, user_agent: str, timeout: float, max_bytes: int) -> tuple[str, str, str]:
    req = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(req, timeout=timeout) as response:
        final_url = response.geturl()
        content_type = response.headers.get("Content-Type", "")
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            body = body[:max_bytes]
        text = body.decode(charset, errors="replace")
        return final_url, content_type.lower(), text


def parse_sitemap(url: str, *, user_agent: str, timeout: float) -> tuple[set[str], set[str]]:
    req = Request(url, headers={"User-Agent": user_agent, "Accept": "application/xml,text/xml,*/*"})
    with urlopen(req, timeout=timeout) as response:
        body = response.read()

    root = ET.fromstring(body)
    urls: set[str] = set()
    nested_sitemaps: set[str] = set()

    for elem in root.iter():
        if elem.tag.endswith("loc") and elem.text:
            normalized = normalize_url(elem.text, drop_tracking=False)
            if normalized:
                if normalized.endswith(".xml"):
                    nested_sitemaps.add(normalized)
                else:
                    urls.add(normalized)
    return urls, nested_sitemaps


def canonicalize_page_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", "", ""))


def discover_sitemaps(base_url: str, *, user_agent: str, timeout: float) -> list[str]:
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    seeds: list[str] = [
        f"{root}/sitemap.xml",
        f"{root}/sitemap_index.xml",
        f"{root}/sitemaps.xml",
    ]
    robots_url = f"{root}/robots.txt"
    try:
        req = Request(robots_url, headers={"User-Agent": user_agent, "Accept": "text/plain,*/*"})
        with urlopen(req, timeout=timeout) as response:
            robots_text = response.read().decode("utf-8", errors="replace")
        for line in robots_text.splitlines():
            line = line.strip()
            if not line.lower().startswith("sitemap:"):
                continue
            value = line.split(":", 1)[1].strip()
            normalized = normalize_url(value, drop_tracking=False)
            if normalized:
                seeds.append(normalized)
    except Exception:
        pass

    deduped: list[str] = []
    seen: set[str] = set()
    for url in seeds:
        normalized = normalize_url(url, drop_tracking=False)
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


def discover_urls(
    *,
    start_url: str,
    domain_suffix: str,
    user_agent: str,
    timeout: float,
    delay: float,
    max_crawl_pages: int,
    max_sitemap_files: int,
) -> dict[str, set[str] | list[dict[str, str]]]:
    internal_urls: set[str] = set()
    page_urls: set[str] = set()
    external_assets: set[str] = set()
    fetch_errors: list[dict[str, str]] = []

    sitemap_urls = discover_sitemaps(start_url, user_agent=user_agent, timeout=timeout)
    sitemap_queue = deque(sitemap_urls)
    seen_sitemaps: set[str] = set()
    sitemap_files_processed = 0

    while sitemap_queue and sitemap_files_processed < max_sitemap_files:
        sitemap_url = sitemap_queue.popleft()
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        sitemap_files_processed += 1
        try:
            urls, nested = parse_sitemap(sitemap_url, user_agent=user_agent, timeout=timeout)
            for url in urls:
                if is_internal(url, domain_suffix):
                    internal_urls.add(url)
                    if likely_html(url):
                        page_urls.add(url)
            for nested_url in nested:
                if nested_url not in seen_sitemaps:
                    sitemap_queue.append(nested_url)
        except Exception as exc:
            fetch_errors.append({"url": sitemap_url, "error": str(exc)})
        time.sleep(delay)

    print(
        f"Sitemap discovery complete: {len(page_urls)} internal pages from {sitemap_files_processed} sitemap files.",
        flush=True,
    )

    normalized_start = normalize_url(start_url)
    if normalized_start:
        internal_urls.add(normalized_start)
        page_urls.add(canonicalize_page_url(normalized_start))

    crawl_queue: deque[str] = deque(sorted(page_urls))
    seen_pages: set[str] = set()
    queued_pages: set[str] = set(crawl_queue)

    while crawl_queue and len(seen_pages) < max_crawl_pages:
        current = crawl_queue.popleft()
        queued_pages.discard(current)
        if current in seen_pages:
            continue
        seen_pages.add(current)

        try:
            final_url, content_type, html = fetch_url(
                current,
                user_agent=user_agent,
                timeout=timeout,
                max_bytes=4_000_000,
            )
        except Exception as exc:
            fetch_errors.append({"url": current, "error": str(exc)})
            time.sleep(delay)
            continue

        normalized_final = normalize_url(final_url)
        if normalized_final and is_internal(normalized_final, domain_suffix):
            internal_urls.add(normalized_final)
            if likely_html(normalized_final):
                page_urls.add(canonicalize_page_url(normalized_final))

        if "html" not in content_type and "xml" not in content_type:
            time.sleep(delay)
            continue

        extractor = LinkExtractor()
        try:
            extractor.feed(html)
        except Exception:
            pass

        raw_urls = set(extractor.urls)
        raw_urls.update(ABSOLUTE_URL_RE.findall(html))

        for raw in raw_urls:
            absolute = normalize_url(urljoin(final_url, raw))
            if not absolute:
                continue
            if is_internal(absolute, domain_suffix):
                internal_urls.add(absolute)
                if likely_html(absolute):
                    page_candidate = canonicalize_page_url(absolute)
                    page_urls.add(page_candidate)
                    if page_candidate not in seen_pages and page_candidate not in queued_pages:
                        crawl_queue.append(page_candidate)
                        queued_pages.add(page_candidate)
            elif likely_asset(absolute):
                external_assets.add(absolute)
        if len(seen_pages) % 50 == 0:
            print(
                f"Crawled {len(seen_pages)} pages. Queue={len(crawl_queue)} "
                f"Internal URLs={len(internal_urls)} External assets={len(external_assets)}",
                flush=True,
            )
        time.sleep(delay)

    resource_urls = sorted(u for u in internal_urls if u not in page_urls)
    return {
        "internal_urls": internal_urls,
        "page_urls": page_urls,
        "resource_urls": set(resource_urls),
        "external_assets": external_assets,
        "fetch_errors": fetch_errors,
    }


def write_sorted_lines(path: Path, values: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sorted(set(values))) + "\n", encoding="utf-8")


def run_wget(command: list[str], *, dry_run: bool) -> int:
    if dry_run:
        print("DRY RUN:", " ".join(command))
        return 0
    proc = subprocess.run(command, check=False)
    return proc.returncode


def parse_wget_errors(log_path: Path) -> list[str]:
    if not log_path.exists():
        return []
    errors: list[str] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if "ERROR" in stripped or "failed:" in stripped:
            errors.append(stripped)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Mirror anthropic.com pages and assets locally.")
    parser.add_argument("--start-url", default="https://www.anthropic.com/", help="Entry URL to mirror.")
    parser.add_argument(
        "--domain-suffix",
        default="anthropic.com",
        help="Treat hosts ending with this suffix as internal.",
    )
    parser.add_argument(
        "--output-dir",
        default="mirror",
        help="Directory where mirrored files will be written.",
    )
    parser.add_argument(
        "--work-dir",
        default="work/mirror",
        help="Directory for intermediate URL lists and logs.",
    )
    parser.add_argument("--max-crawl-pages", type=int, default=1000, help="Maximum HTML pages to crawl.")
    parser.add_argument("--max-sitemap-files", type=int, default=50, help="Maximum sitemap XML files to parse.")
    parser.add_argument("--timeout", type=float, default=30.0, help="Network timeout in seconds.")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.15,
        help="Delay between discovery requests to avoid hammering the site.",
    )
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="User agent string.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover URLs and print download commands without running wget.",
    )
    args = parser.parse_args()

    if shutil.which("wget") is None:
        print("ERROR: wget is required but not installed.", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir).resolve()
    work_dir = Path(args.work_dir).resolve()
    discovery_dir = work_dir / "discovery"
    logs_dir = work_dir / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    discovery_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    print("Discovering URLs from sitemap and in-page links...")
    discovered = discover_urls(
        start_url=args.start_url,
        domain_suffix=args.domain_suffix,
        user_agent=args.user_agent,
        timeout=args.timeout,
        delay=args.delay,
        max_crawl_pages=args.max_crawl_pages,
        max_sitemap_files=args.max_sitemap_files,
    )

    page_urls = sorted(discovered["page_urls"])
    resource_urls = sorted(discovered["resource_urls"])
    external_assets = sorted(discovered["external_assets"])
    internal_urls = sorted(discovered["internal_urls"])
    fetch_errors = discovered["fetch_errors"]

    pages_file = discovery_dir / "pages.txt"
    resources_file = discovery_dir / "resources.txt"
    external_assets_file = discovery_dir / "external_assets.txt"
    internal_urls_file = discovery_dir / "internal_urls.txt"
    all_download_urls_file = discovery_dir / "all_download_urls.txt"
    domains_file = discovery_dir / "domains.txt"

    all_download_urls = sorted(set(page_urls) | set(resource_urls) | set(external_assets))
    domains = sorted({urlparse(url).hostname for url in all_download_urls if urlparse(url).hostname})

    write_sorted_lines(pages_file, page_urls)
    write_sorted_lines(resources_file, resource_urls)
    write_sorted_lines(external_assets_file, external_assets)
    write_sorted_lines(internal_urls_file, internal_urls)
    write_sorted_lines(all_download_urls_file, all_download_urls)
    write_sorted_lines(domains_file, domains)

    domains_csv = ",".join(domains)
    pages_log = logs_dir / "wget-pages.log"
    resources_log = logs_dir / "wget-resources.log"

    wget_common = [
        "wget",
        "--directory-prefix",
        str(output_dir),
        "--force-directories",
        "--content-disposition",
        "--trust-server-names",
        "--convert-links",
        "--adjust-extension",
        "--backup-converted",
        "--span-hosts",
        "--domains",
        domains_csv,
        "--timestamping",
        "--continue",
        "--tries=3",
        "--timeout=30",
        "--wait=0.15",
        "--random-wait",
        "--retry-connrefused",
        "--execute",
        "robots=on",
        "--user-agent",
        args.user_agent,
        "--no-verbose",
    ]

    pages_cmd = wget_common + [
        "--page-requisites",
        "--input-file",
        str(pages_file),
        "-o",
        str(pages_log),
    ]
    resources_cmd = wget_common + [
        "--input-file",
        str(resources_file),
        "-o",
        str(resources_log),
    ]

    print(f"Discovered {len(page_urls)} pages, {len(resource_urls)} internal resources, and {len(external_assets)} external assets.")
    print("Downloading pages + page requisites...")
    pages_rc = run_wget(pages_cmd, dry_run=args.dry_run)
    print("Downloading additional direct resources...")
    resources_rc = run_wget(resources_cmd, dry_run=args.dry_run)

    page_errors = parse_wget_errors(pages_log)
    resource_errors = parse_wget_errors(resources_log)

    mirrored_files = [p for p in output_dir.rglob("*") if p.is_file()]
    report = {
        "start_url": args.start_url,
        "generated_at_epoch": int(time.time()),
        "counts": {
            "pages": len(page_urls),
            "internal_urls": len(internal_urls),
            "internal_resources": len(resource_urls),
            "external_assets": len(external_assets),
            "download_domains": len(domains),
            "mirrored_files": len(mirrored_files),
            "fetch_errors": len(fetch_errors),
            "wget_page_error_lines": len(page_errors),
            "wget_resource_error_lines": len(resource_errors),
        },
        "artifacts": {
            "pages_file": str(pages_file),
            "resources_file": str(resources_file),
            "external_assets_file": str(external_assets_file),
            "internal_urls_file": str(internal_urls_file),
            "all_download_urls_file": str(all_download_urls_file),
            "domains_file": str(domains_file),
            "wget_pages_log": str(pages_log),
            "wget_resources_log": str(resources_log),
        },
        "fetch_errors": fetch_errors[:200],
        "wget_error_samples": (page_errors + resource_errors)[:200],
    }
    report_path = work_dir / "mirror_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Report written to: {report_path}")
    if pages_rc != 0 or resources_rc != 0:
        print("Mirror completed with wget errors. Check logs and report for details.")
        return 1

    print("Mirror completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
