import { promises as fs } from "fs";
import path from "path";
import { NextRequest } from "next/server";

const SNAPSHOT_ROOT = path.join(process.cwd(), "reference", "www.anthropic.com");

const MIME_BY_EXT: Record<string, string> = {
  ".avif": "image/avif",
  ".css": "text/css; charset=utf-8",
  ".gif": "image/gif",
  ".html": "text/html; charset=utf-8",
  ".ico": "image/x-icon",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".mp4": "video/mp4",
  ".pdf": "application/pdf",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".txt": "text/plain; charset=utf-8",
  ".webm": "video/webm",
  ".webp": "image/webp",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".xml": "application/xml; charset=utf-8",
};

function getMimeType(filePath: string): string {
  const ext = path.extname(filePath).toLowerCase();
  return MIME_BY_EXT[ext] ?? "application/octet-stream";
}

async function exists(filePath: string): Promise<boolean> {
  try {
    const stat = await fs.stat(filePath);
    return stat.isFile();
  } catch {
    return false;
  }
}

function sanitizePath(rawPath: string): string {
  const normalized = path.posix.normalize(`/${rawPath}`).replace(/^\/+/, "");
  if (normalized.startsWith("../") || normalized === "..") {
    return "";
  }
  return normalized;
}

async function resolveSnapshotFile(requestPath: string): Promise<string | null> {
  const cleanedPath = sanitizePath(requestPath);
  const hasExt = path.posix.extname(cleanedPath) !== "";
  const trimmed = cleanedPath.replace(/\/+$/, "");

  const candidates = new Set<string>();
  if (!trimmed) {
    candidates.add("index.html");
  } else {
    candidates.add(trimmed);
    if (!hasExt) {
      candidates.add(`${trimmed}.html`);
      candidates.add(path.posix.join(trimmed, "index.html"));
    }
  }

  for (const candidate of candidates) {
    const absolute = path.join(SNAPSHOT_ROOT, candidate);
    if (!absolute.startsWith(SNAPSHOT_ROOT)) {
      continue;
    }
    if (await exists(absolute)) {
      return absolute;
    }
  }

  return null;
}

async function serveFile(requestPath: string, headOnly: boolean): Promise<Response> {
  const snapshotFile = await resolveSnapshotFile(requestPath);
  if (!snapshotFile) {
    return new Response("Not Found", { status: 404 });
  }

  const headers = new Headers({
    "cache-control": "public, max-age=0",
    "content-type": getMimeType(snapshotFile),
  });

  if (headOnly) {
    return new Response(null, { headers });
  }

  const body = await fs.readFile(snapshotFile);
  return new Response(body, { headers });
}

function getRequestPath(request: NextRequest): string {
  return request.nextUrl.pathname.replace(/^\/www\.anthropic\.com\/?/, "");
}

export async function GET(request: NextRequest): Promise<Response> {
  return serveFile(getRequestPath(request), false);
}

export async function HEAD(request: NextRequest): Promise<Response> {
  return serveFile(getRequestPath(request), true);
}
