export function isApiError(e) {
  return e && typeof e === "object" && (e.error || e.detail || e.message);
}

const LOCAL_LIKE_HOSTS = new Set(['localhost', '127.0.0.1', '0.0.0.0', '::1', '[::1]']);

function deriveApiOriginFromWindowOrigin() {
  if (typeof window === 'undefined' || !window.location?.origin) {
    return '';
  }

  const fallback = window.location.origin.replace(/\/+$/, '');

  try {
    const url = new URL(window.location.origin);
    const { protocol, hostname } = url;
    const lowerHost = hostname.toLowerCase();
    const makeOrigin = (host, keepPort = false) => {
      const port = keepPort && url.port ? `:${url.port}` : '';
      return `${protocol}//${host}${port}`.replace(/\/+$/, '');
    };

    const swapSubdomain = (prefix) => {
      const needle = `${prefix}.`;
      return lowerHost.startsWith(needle) ? `api.${hostname.slice(needle.length)}` : null;
    };

    const swapped =
      swapSubdomain('app') ||
      swapSubdomain('dashboard') ||
      swapSubdomain('www');

    if (swapped) {
      return makeOrigin(swapped);
    }

    if (lowerHost === 'getpodcastplus.com') {
      return makeOrigin('api.getpodcastplus.com');
    }

    const hostSegments = lowerHost.split('.');
    if (
      !lowerHost.startsWith('api.') &&
      !LOCAL_LIKE_HOSTS.has(lowerHost) &&
      hostSegments.length === 2
    ) {
      return makeOrigin(`api.${hostname}`);
    }

    return makeOrigin(hostname, true);
  } catch (err) {
    if (fallback.includes('//getpodcastplus.com')) {
      return fallback.replace('://', '://api.');
    }
  }

  return fallback;
}

export function resolveRuntimeApiBase() {
  const envBase = (import.meta && import.meta.env && (import.meta.env.VITE_API_BASE || import.meta.env.VITE_API_BASE_URL))
    ? String(import.meta.env.VITE_API_BASE || import.meta.env.VITE_API_BASE_URL).replace(/\/+$/, '')
    : '';
  if (envBase) return envBase;
  const derived = deriveApiOriginFromWindowOrigin();
  // Hard fallback to prod API to avoid silent misroutes when derivation fails
  return derived || 'https://api.getpodcastplus.com';
}

// Base URL for API requests. In dev, you can leave this blank and rely on Vite's /api proxy.
const runtimeBase = resolveRuntimeApiBase();

export function buildApiUrl(path) {
  const base = runtimeBase;
  if (!path) return base || '';
  if (/^https?:\/\//i.test(path)) return path; // already absolute
  return base ? `${base}${path}` : path;
}

async function req(path, opts = {}) {
  const url = buildApiUrl(path);
  const res = await fetch(url, {
    credentials: "include",
    headers: { ...(opts.headers || {}) },
    ...opts,
  });
  // Try to parse JSON if content-type hints it, otherwise allow empty
  const ct = res.headers.get && res.headers.get("content-type");
  const canJson = ct && ct.includes("application/json");
  const data = canJson ? await res.json().catch(() => ({})) : await res.text().catch(() => "");
  if (!res.ok) {
    if (canJson) {
      const payload = (data && typeof data === 'object') ? data : { message: String(data || 'Request failed') };
      throw { status: res.status, ...payload };
    }
    throw { status: res.status, message: String(data || "Request failed") };
  }
  return canJson ? data : { ok: true, data };
}

function jsonBody(body) {
  return body === undefined || body === null ? undefined : JSON.stringify(body);
}

export function makeApi(token) {
  // Compute Authorization header at call time so callers that provided a
  // null/undefined token initially still pick up a token stored later in
  // localStorage (e.g., after OAuth redirect). This avoids races where
  // components call makeApi before AuthProvider has set its token state.
  const authFor = (optsHeaders = {}) => {
    const provided = token || (() => { try { return localStorage.getItem('authToken'); } catch { return null; } })();
    return provided ? { Authorization: `Bearer ${provided}`, ...(optsHeaders || {}) } : { ...(optsHeaders || {}) };
  };

  return {
    get: (p, opts={}) => req(p, { ...opts, method: "GET", headers: authFor(opts.headers) }),
    post: (p, body, opts={}) => req(p, { ...opts, method: "POST", headers: authFor({ 'Content-Type': 'application/json', ...(opts.headers||{}) }), body: jsonBody(body) }),
    put: (p, body, opts={}) => req(p, { ...opts, method: "PUT", headers: authFor({ 'Content-Type': 'application/json', ...(opts.headers||{}) }), body: jsonBody(body) }),
    patch: (p, body, opts={}) => req(p, { ...opts, method: "PATCH", headers: authFor({ 'Content-Type': 'application/json', ...(opts.headers||{}) }), body: jsonBody(body) }),
    del: (p, opts={}) => req(p, { ...opts, method: "DELETE", headers: authFor(opts.headers) }),
    raw: (p, opts={}) => req(p, { ...opts, headers: authFor(opts.headers) }),
  };
}

export function assetUrl(path) {
  // Build a full URL for static assets that come from the API origin (e.g., /static or cover paths)
  return buildApiUrl(path);
}

// Backward-compatible simple API without auth
export const api = {
  get: (p, opts) => req(p, { ...(opts||{}), method: "GET" }),
  post: (p, body, opts) => req(p, { ...(opts||{}), method: "POST", headers: { 'Content-Type': 'application/json', ...((opts&&opts.headers)||{}) }, body: jsonBody(body) }),
};
