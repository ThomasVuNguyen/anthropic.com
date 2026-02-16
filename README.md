# anthropic.com Mirror Toolkit

Local tooling to create a high-fidelity mirror of `https://www.anthropic.com/` for offline study/design reference.

## What It Does

- Discovers URLs from `robots.txt` + sitemap XML files.
- Crawls internal HTML pages to find additional links/resources.
- Downloads pages with `wget --page-requisites` (CSS/JS/images/fonts/etc.).
- Runs a second pass for direct resource URLs.
- Generates a report with coverage/error counts.

## Usage

```bash
python3 scripts/mirror_anthropic.py \
  --start-url https://www.anthropic.com/ \
  --output-dir mirror \
  --work-dir work/mirror

# Keep internal anthropic.com links/routes on the local mirror
python3 scripts/localize_mirror.py \
  --mirror-dir mirror \
  --primary-host www.anthropic.com
```

## Key Outputs

- Mirrored site: `mirror/`
- Discovery lists: `work/mirror/discovery/`
- Wget logs: `work/mirror/logs/`
- Summary report: `work/mirror/mirror_report.json`

## Notes

- This targets public pages and assets only.
- Some elements may still differ offline if they rely on live APIs, dynamic personalization, or blocked third-party resources.
