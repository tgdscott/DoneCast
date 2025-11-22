export function isApiError(e) {
  return e && typeof e === "object" && (e.error || e.detail || e.message);
}

const LOCAL_LIKE_HOSTS = new Set(['localhost', '127.0.0.1', '0.0.0.0', '::1', '[::1]']);

const ABSOLUTE_URL_PATTERN = /^[a-z][a-z0-9+.-]*:/i;
const PLAYBACK_TOKEN_PATTERN = /\/api\/episodes\/[^/?#]+\/playback(?:[/?#]|$)/i;

function getGlobalLocalStorage() {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      return window.localStorage;
    }
  } catch {
    /* ignore */
  }
  try {
    if (typeof localStorage !== 'undefined') {
      return localStorage;
    }
  } catch {
    /* ignore */
  }
  return null;
}

export function getStoredAuthToken() {
  const storage = getGlobalLocalStorage();
  if (!storage) return null;
  try {
    const token = storage.getItem('authToken');
    return token || null;
  } catch {
    return null;
  }
}

function shouldAttachToken(path) {
  if (!path || typeof path !== 'string') return false;
  return PLAYBACK_TOKEN_PATTERN.test(path);
}

function appendTokenIfNeeded(url) {
  if (!shouldAttachToken(url)) return url;
  const token = getStoredAuthToken();
  if (!token) return url;

  try {
    const isAbsolute = ABSOLUTE_URL_PATTERN.test(url) || url.startsWith('//');
    const base = isAbsolute ? undefined : 'http://placeholder.local';
    const urlObj = new URL(url, base);
    urlObj.searchParams.set('token', token);

    if (isAbsolute) {
      return urlObj.toString();
    }
    const pathname = urlObj.pathname || '';
    const search = urlObj.search || '';
    const hash = urlObj.hash || '';
    return `${pathname}${search}${hash}` || pathname;
  } catch {
    const hashIndex = url.indexOf('#');
    let baseUrl = url;
    let hash = '';
    if (hashIndex >= 0) {
      baseUrl = url.slice(0, hashIndex);
      hash = url.slice(hashIndex);
    }
    const separator = baseUrl.includes('?') ? '&' : '?';
    return `${baseUrl}${separator}token=${encodeURIComponent(token)}${hash}`;
  }
}

function deriveApiOriginFromWindowOrigin() {
  if (typeof window === 'undefined' || typeof window.location === 'undefined') {
    return '';
  }
  const host = window.location.hostname || '';
  if (LOCAL_LIKE_HOSTS.has(host)) {
    return '';
  }
  // Default production API host when no build-time override is provided.
  return 'https://api.podcastplusplus.com';
}

export function resolveRuntimeApiBase() {
  const envBase = (import.meta && import.meta.env && (import.meta.env.VITE_API_BASE || import.meta.env.VITE_API_BASE_URL))
    ? String(import.meta.env.VITE_API_BASE || import.meta.env.VITE_API_BASE_URL).replace(/\/+$/, '')
    : '';
  if (envBase) return envBase;
  // Use same-origin by default; front proxies should route /api → backend.
  return deriveApiOriginFromWindowOrigin();
}

// Base URL for API requests. In dev, you can leave this blank and rely on Vite's /api proxy.
const runtimeBase = resolveRuntimeApiBase();

export function coerceArray(payload) {
  if (Array.isArray(payload)) return payload;
  if (!payload || typeof payload !== 'object') return [];
  if (Array.isArray(payload.items)) return payload.items;
  if (Array.isArray(payload.results)) return payload.results;
  if (Array.isArray(payload.data)) return payload.data;
  if (Array.isArray(payload.records)) return payload.records;
  return [];
}

export function buildApiUrl(path) {
  const base = runtimeBase;
  if (!path) return base || '';
  if (/^https?:\/\//i.test(path)) return path; // already absolute

  const rawPath = path;
  const normalizedPath = rawPath.startsWith('/') ? rawPath : `/${rawPath}`;

  if (!base) return rawPath;

  const trimmedBase = base.replace(/\/+$/, '');
  const assetPrefixes = ['/static', '/media', '/storage', '/final'];
  const isAssetPath = assetPrefixes.some((prefix) =>
    normalizedPath === prefix ||
    normalizedPath.startsWith(`${prefix}/`) ||
    normalizedPath.startsWith(`${prefix}?`) ||
    normalizedPath.startsWith(`${prefix}#`) ||
    normalizedPath.startsWith(`${prefix}&`)
  );

  const baseHandlesApi = trimmedBase.endsWith('/api');
  const isAbsoluteBase = /^[a-zA-Z][a-zA-Z\d+\-.]*:\/\//.test(trimmedBase);
  if (baseHandlesApi) {
    if (normalizedPath === '/api') {
      return trimmedBase;
    }
    if (normalizedPath === '/api/') {
      return `${trimmedBase}/`;
    }
    if (normalizedPath.startsWith('/api/')) {
      return `${trimmedBase}${normalizedPath.slice(4)}`;
    }
    if (normalizedPath.startsWith('/api?') || normalizedPath.startsWith('/api#') || normalizedPath.startsWith('/api&')) {
      return `${trimmedBase}${normalizedPath.slice(4)}`;
    }

    if (isAssetPath) {
      if (!isAbsoluteBase) {
        return `${trimmedBase}${normalizedPath}`;
      }
      const rootBase = trimmedBase.slice(0, -4); // strip trailing "/api"
      if (!rootBase) {
        return normalizedPath;
      }
      if (normalizedPath === '/') {
        return rootBase;
      }
      return `${rootBase}${normalizedPath}`;
    }
  }

  if (normalizedPath === '/') {
    return trimmedBase;
  }

  return `${trimmedBase}${normalizedPath}`;
}

// Global warmup callback - set by WarmupProvider
let warmupStartRequest = null;
let warmupEndRequest = null;

export function setWarmupCallbacks(start, end) {
  warmupStartRequest = start;
  warmupEndRequest = end;
}

async function req(path, opts = {}) {
  const url = buildApiUrl(path);
  const requestId = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  
  // Exclude upload endpoints from warmup tracking - these are expected to take time
  // Upload endpoints have progress indicators, so users know they're working
  const isUploadRequest = path && (
    path.includes('/upload/') ||
    path.includes('/media/upload') ||
    path.includes('/merge') ||
    opts.body instanceof FormData
  );
  
  // Start tracking if warmup callbacks are available (but not for uploads)
  if (warmupStartRequest && !isUploadRequest) {
    warmupStartRequest(requestId);
  }
  
  try {
    // When FormData is used, don't set Content-Type - let browser set it with boundary
    const isFormData = opts.body instanceof FormData;
    const headers = { ...(opts.headers || {}) };
    if (isFormData && headers['Content-Type']) {
      delete headers['Content-Type'];
    }
    
    const res = await fetch(url, {
      credentials: "include",
      headers,
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
  } finally {
    // End tracking when request completes (success or failure) - but not for uploads
    if (warmupEndRequest && !isUploadRequest) {
      warmupEndRequest(requestId);
    }
  }
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
    const provided = token || getStoredAuthToken();
    return provided ? { Authorization: `Bearer ${provided}`, ...(optsHeaders || {}) } : { ...(optsHeaders || {}) };
  };

  return {
    get: (p, opts={}) => req(p, { ...opts, method: "GET", headers: authFor(opts.headers) }),
    post: (p, body, opts={}) => req(p, { ...opts, method: "POST", headers: authFor({ 'Content-Type': 'application/json', ...(opts.headers||{}) }), body: jsonBody(body) }),
    put: (p, body, opts={}) => req(p, { ...opts, method: "PUT", headers: authFor({ 'Content-Type': 'application/json', ...(opts.headers||{}) }), body: jsonBody(body) }),
    patch: (p, body, opts={}) => req(p, { ...opts, method: "PATCH", headers: authFor({ 'Content-Type': 'application/json', ...(opts.headers||{}) }), body: jsonBody(body) }),
    del: (p, body, opts={}) => req(p, { ...opts, method: "DELETE", headers: authFor({ 'Content-Type': 'application/json', ...(opts.headers||{}) }), body: jsonBody(body) }),
    raw: (p, opts={}) => {
      // When FormData is used, don't set Content-Type - let the browser set it with boundary
      const isFormData = opts.body instanceof FormData;
      const headers = isFormData 
        ? authFor({ ...(opts.headers || {}) }) // Don't set Content-Type for FormData
        : authFor(opts.headers);
      // Remove Content-Type from headers if FormData is detected (browser will set it)
      if (isFormData && headers['Content-Type']) {
        delete headers['Content-Type'];
      }
      return req(p, { ...opts, headers });
    },
  };
}

export function assetUrl(path) {
  // Build a full URL for static assets that come from the API origin (e.g., /static or cover paths)
  const built = buildApiUrl(path);
  return appendTokenIfNeeded(built);
}

// Backward-compatible simple API without auth
export const api = {
  get: (p, opts) => req(p, { ...(opts||{}), method: "GET" }),
  post: (p, body, opts) => req(p, { ...(opts||{}), method: "POST", headers: { 'Content-Type': 'application/json', ...((opts&&opts.headers)||{}) }, body: jsonBody(body) }),
};

