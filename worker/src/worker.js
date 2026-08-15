/**
 * data.inno-forum.co.uk — participant-facing data edge.
 *
 * WHY THIS EXISTS (not cosmetic — it is load-bearing):
 *
 *   GitHub release assets are unusable from browser JavaScript. The download URL is a 302
 *   to an S3 blob; CORS pre-flight (OPTIONS) does not follow redirects, and the blob sends
 *   no Access-Control-Allow-Origin. So DuckDB-WASM, Observable and every JS charting
 *   library fail against a raw release URL — which is exactly the zero-install path the
 *   programme promises to non-coders.
 *
 *   This Worker terminates the pre-flight itself, follows the redirect server-side, and
 *   re-emits the bytes with permissive CORS. It also:
 *     · gives branded, stable URLs that never name the hosting account, so the GitHub org
 *       can change without breaking a single published link
 *     · forwards Range requests, so DuckDB reads one column of a remote parquet instead
 *       of downloading the file
 *     · caches at the edge, absorbing the event-morning spike
 *
 * URL SHAPE
 *   https://data.inno-forum.co.uk/<challenge>/<version>/<path...>
 *     → github.com/<OWNER>/<REPO>/releases/download/<challenge>-<version>/<flattened>
 *
 *   Release assets are a FLAT namespace, so nested paths are flattened with "__":
 *     /c01-one-farm-one-picture/v2027-06-01/gold/farm_daily.parquet
 *     → tag "c01-one-farm-one-picture-v2027-06-01", asset "gold__farm_daily.parquet"
 *
 *   /<challenge>/latest.json and /manifest.json resolve against the "latest" tag.
 */

const OWNER = 'Innovation-forum-Cambridgeshire';
const REPO = 'hackathon-data';

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
  'Access-Control-Allow-Headers': 'Range, Content-Type, If-None-Match, If-Range',
  // Without this, JS cannot read Content-Length/Content-Range — DuckDB-WASM needs both
  // to plan its range reads, and silently misbehaves if they are hidden.
  'Access-Control-Expose-Headers':
    'Content-Length, Content-Range, Content-Type, ETag, Accept-Ranges, Last-Modified',
  'Access-Control-Max-Age': '86400',
};

const TEXTUAL = {
  json: 'application/json; charset=utf-8',
  csv: 'text/csv; charset=utf-8',
  md: 'text/markdown; charset=utf-8',
  txt: 'text/plain; charset=utf-8',
  jsonl: 'application/x-ndjson; charset=utf-8',
  parquet: 'application/vnd.apache.parquet',
  pdf: 'application/pdf',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
};

function contentTypeFor(path) {
  const ext = path.split('.').pop().toLowerCase();
  return TEXTUAL[ext] || 'application/octet-stream';
}

function withCors(headers = {}) {
  return { ...CORS, ...headers };
}

function json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body, null, 2), {
    status,
    headers: withCors({ 'Content-Type': TEXTUAL.json, ...extra }),
  });
}

/** Map a public path onto a GitHub release tag + flat asset name. */
function resolve(pathname) {
  const parts = pathname.replace(/^\/+/, '').split('/').filter(Boolean);

  // Root-level well-known files live on the "catalogue" release.
  if (parts.length === 1 && ['manifest.json', 'llms.txt', 'index.json'].includes(parts[0])) {
    return { tag: 'catalogue-latest', asset: parts[0] };
  }
  if (parts.length < 2) return null;

  const [challenge, second, ...rest] = parts;

  // /<challenge>/latest.json — a tiny pointer, published on a per-challenge "latest" tag.
  if (second === 'latest.json' && rest.length === 0) {
    return { tag: `${challenge}-latest`, asset: 'latest.json' };
  }

  // /<challenge>/<version>/<nested/path>
  if (rest.length === 0) return null;
  if (!/^v[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(second)) return null; // reject junk early

  return { tag: `${challenge}-${second}`, asset: rest.join('__') };
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // 1. Terminate the pre-flight here. This is the whole reason the Worker exists —
    //    forwarding it to GitHub is precisely what fails.
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: withCors() });
    }

    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return json({ error: 'method_not_allowed', allowed: ['GET', 'HEAD', 'OPTIONS'] }, 405);
    }

    if (url.pathname === '/' || url.pathname === '/index.html') {
      return json({
        service: 'Innovation Forum hackathon data',
        docs: `https://github.com/${OWNER}/${REPO}`,
        usage: {
          duckdb: `SELECT * FROM read_parquet('${url.origin}/<challenge>/<version>/gold/<table>.parquet')`,
          manifest: `${url.origin}/manifest.json`,
          llms: `${url.origin}/llms.txt`,
        },
      });
    }

    const target = resolve(url.pathname);
    if (!target) {
      return json(
        {
          error: 'not_found',
          hint: 'Expected /<challenge>/<version>/<path>, e.g. /c02-mapping-the-gaps/v2026-10-01/gold/deprivation.parquet',
          manifest: `${url.origin}/manifest.json`,
        },
        404
      );
    }

    const upstream = `https://github.com/${OWNER}/${REPO}/releases/download/${target.tag}/${target.asset}`;

    // 2. Edge cache. Keyed on the upstream URL plus Range, because a cached full-body
    //    response must never be handed back to a client that asked for bytes 0-1023.
    const range = request.headers.get('Range');
    const cacheKey = new Request(upstream + (range ? `#range=${range}` : ''), { method: 'GET' });
    const cache = caches.default;

    let response = await cache.match(cacheKey);

    if (!response) {
      const upstreamHeaders = {};
      if (range) upstreamHeaders['Range'] = range;

      const origin = await fetch(upstream, {
        method: 'GET', // always GET upstream; we strip the body below for HEAD
        headers: upstreamHeaders,
        redirect: 'follow', // server-side redirect follow — the browser cannot do this
        cf: { cacheEverything: true, cacheTtl: 3600 },
      });

      if (origin.status === 404) {
        return json(
          {
            error: 'asset_not_found',
            tag: target.tag,
            asset: target.asset,
            hint: 'Check the version exists. Versions are immutable; see <challenge>/latest.json',
          },
          404
        );
      }
      if (!origin.ok && origin.status !== 206) {
        return json({ error: 'upstream_error', status: origin.status, tag: target.tag }, 502);
      }

      response = new Response(origin.body, {
        status: origin.status,
        headers: withCors({
          'Content-Type': contentTypeFor(target.asset),
          'Accept-Ranges': 'bytes',
          // Versions are immutable, so cache hard. The only mutable objects are the
          // *-latest tags, which get a short TTL instead.
          'Cache-Control': target.tag.endsWith('-latest')
            ? 'public, max-age=300'
            : 'public, max-age=31536000, immutable',
          'X-Data-Source': `${target.tag}/${target.asset}`,
        }),
      });

      for (const h of ['Content-Length', 'Content-Range', 'ETag', 'Last-Modified']) {
        const v = origin.headers.get(h);
        if (v) response.headers.set(h, v);
      }

      if (response.status === 200 || response.status === 206) {
        ctx.waitUntil(cache.put(cacheKey, response.clone()));
      }
    }

    if (request.method === 'HEAD') {
      return new Response(null, { status: response.status, headers: response.headers });
    }
    return response;
  },
};
