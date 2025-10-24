import { makeApi } from './apiClient';

function toArray(value) {
  if (Array.isArray(value)) return value;
  if (!value || typeof value !== 'object') return [];
  if (Array.isArray(value.items)) return value.items;
  if (Array.isArray(value.results)) return value.results;
  if (Array.isArray(value.data)) return value.data;
  if (Array.isArray(value.records)) return value.records;
  if (Array.isArray(value.files)) return value.files;
  return [];
}

function uploadWithXmlHttpRequest(url, file, headers = {}, { onProgress, signal, onXhrCreate } = {}) {
  if (typeof XMLHttpRequest === 'undefined') {
    return fetch(url, {
      method: 'PUT',
      headers,
      body: file,
    }).then((res) => {
      if (!res.ok) {
        throw new Error(`Upload failed with status ${res.status}`);
      }
      return true;
    });
  }

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const startTime = Date.now();
    let lastLoaded = 0;
    let lastTime = startTime;
    let smoothedSpeed = null;
    let abortHandler;
    try {
      xhr.open('PUT', url);
    } catch (err) {
      reject(err);
      return;
    }
    if (onXhrCreate && typeof onXhrCreate === 'function') {
      try { onXhrCreate(xhr); } catch (_) { /* ignore */ }
    }
    if (signal) {
      if (signal.aborted) {
        try { xhr.abort(); } catch (_) { /* ignore */ }
        reject(signal.reason || new DOMException('Upload aborted', 'AbortError'));
        return;
      }
      abortHandler = () => {
        try { xhr.abort(); } catch (_) { /* ignore */ }
        reject(signal.reason || new DOMException('Upload aborted', 'AbortError'));
      };
      signal.addEventListener('abort', abortHandler, { once: true });
    }

    try {
      xhr.withCredentials = false;
    } catch (_) { /* ignore */ }

    if (headers && typeof headers === 'object') {
      Object.entries(headers).forEach(([key, value]) => {
        if (key && value !== undefined && value !== null) {
          try { xhr.setRequestHeader(String(key), String(value)); } catch (_) { /* ignore */ }
        }
      });
    }

    xhr.upload.onprogress = (event) => {
      if (!event || typeof onProgress !== 'function') return;
      const now = Date.now();
      const elapsedSeconds = (now - startTime) / 1000;

      let bytesPerSecond = null;
      let etaSeconds = null;

      if (elapsedSeconds > 0 && event.loaded >= 0) {
        const averageSpeed = event.loaded / elapsedSeconds;
        if (Number.isFinite(averageSpeed) && averageSpeed > 0) {
          bytesPerSecond = averageSpeed;
        }
      }

      const deltaTime = (now - lastTime) / 1000;
      const deltaLoaded = event.loaded - lastLoaded;
      if (deltaTime > 0 && deltaLoaded >= 0) {
        const instantSpeed = deltaLoaded / deltaTime;
        if (Number.isFinite(instantSpeed) && instantSpeed > 0) {
          smoothedSpeed = smoothedSpeed == null
            ? instantSpeed
            : (smoothedSpeed * 0.7) + (instantSpeed * 0.3);
        }
      }

      if (smoothedSpeed == null && bytesPerSecond) {
        smoothedSpeed = bytesPerSecond;
      }

      if (smoothedSpeed && event.lengthComputable && event.total > event.loaded) {
        const remaining = event.total - event.loaded;
        const eta = remaining / smoothedSpeed;
        if (Number.isFinite(eta) && eta >= 0) {
          etaSeconds = eta;
        }
      }

      lastLoaded = event.loaded;
      lastTime = now;

      if (!event.lengthComputable) {
        onProgress({
          loaded: event.loaded,
          total: event.total,
          percent: null,
          bytesPerSecond: smoothedSpeed || bytesPerSecond || null,
          etaSeconds,
        });
        return;
      }
      const percent = event.total > 0 ? Math.min(100, Math.round((event.loaded / event.total) * 100)) : null;
      onProgress({
        loaded: event.loaded,
        total: event.total,
        percent,
        bytesPerSecond: smoothedSpeed || bytesPerSecond || null,
        etaSeconds,
      });
    };

    xhr.onerror = () => {
      reject(new Error('Network error during upload'));
    };

    xhr.onabort = () => {
      reject(new DOMException('Upload aborted', 'AbortError'));
    };

    xhr.onload = () => {
      if (abortHandler && signal) {
        try { signal.removeEventListener('abort', abortHandler); } catch (_) { /* ignore */ }
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(true);
        return;
      }
      // Include status code in error for better error handling upstream
      const error = new Error(`Upload failed with status ${xhr.status}`);
      error.status = xhr.status;
      reject(error);
    };

    try {
      xhr.send(file);
    } catch (err) {
      reject(err);
    }
  });
}

export async function uploadMediaDirect({
  category,
  file,
  friendlyName,
  token,
  apiClient,
  notifyWhenReady,
  notifyEmail,
  onProgress,
  signal,
  onXhrCreate,
} = {}) {
  if (!category) throw new Error('category is required');
  if (!file) throw new Error('file is required');

  const api = apiClient || makeApi(token);
  const contentType = (file.type || '').trim() || 'application/octet-stream';

  let presign;
  let useDirectUpload = true;

  // Try presign endpoint - if it returns 501, fall back to standard upload
  try {
    presign = await api.post(`/api/media/upload/${category}/presign`, {
      filename: file.name || 'upload',
      content_type: contentType,
    });
  } catch (err) {
    // If presign endpoint returns 501 (Not Implemented), fall back to standard upload
    if (err?.response?.status === 501 || err?.status === 501) {
      useDirectUpload = false;
    } else {
      throw err; // Re-throw other errors
    }
  }

  if (useDirectUpload) {
    // Direct GCS upload path
    const uploadUrl = presign?.upload_url || presign?.uploadUrl;
    const objectPath = presign?.object_path || presign?.objectPath;
    const headers = presign?.headers || {};

    if (!uploadUrl || !objectPath) {
      throw new Error('Failed to obtain upload URL');
    }

    await uploadWithXmlHttpRequest(uploadUrl, file, headers, { onProgress, signal, onXhrCreate });

    const registerPayload = {
      uploads: [
        {
          object_path: objectPath,
          friendly_name: friendlyName,
          original_filename: file.name || friendlyName || 'upload',
          content_type: contentType,
          size: typeof file.size === 'number' ? file.size : undefined,
        },
      ],
    };

    if (notifyWhenReady !== undefined) {
      registerPayload.notify_when_ready = !!notifyWhenReady;
    }
    if (notifyEmail) {
      registerPayload.notify_email = notifyEmail;
    }

    const registered = await api.post(`/api/media/upload/${category}/register`, registerPayload);
    return toArray(registered);
  } else {
    // Fallback to standard multipart/form-data upload
    const formData = new FormData();
    formData.append('files', file);
    
    const friendlyNamesArray = [friendlyName || file.name || 'upload'];
    formData.append('friendly_names', JSON.stringify(friendlyNamesArray));
    
    if (notifyWhenReady !== undefined) {
      formData.append('notify_when_ready', notifyWhenReady ? 'true' : 'false');
    }
    if (notifyEmail) {
      formData.append('notify_email', notifyEmail);
    }

    // For standard upload, we need to use XMLHttpRequest to track progress
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      
      if (signal) {
        if (signal.aborted) {
          reject(signal.reason || new DOMException('Upload aborted', 'AbortError'));
          return;
        }
        const abortHandler = () => {
          try { xhr.abort(); } catch (_) { /* ignore */ }
          reject(signal.reason || new DOMException('Upload aborted', 'AbortError'));
        };
        signal.addEventListener('abort', abortHandler, { once: true });
      }

      if (onXhrCreate && typeof onXhrCreate === 'function') {
        try { onXhrCreate(xhr); } catch (_) { /* ignore */ }
      }

      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable && onProgress) {
          const percent = (e.loaded / e.total) * 100;
          onProgress({ percent, loaded: e.loaded, total: e.total });
        }
      });

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const result = JSON.parse(xhr.responseText);
            resolve(toArray(result));
          } catch (err) {
            reject(new Error('Failed to parse upload response'));
          }
        } else {
          const error = new Error(`Upload failed with status ${xhr.status}`);
          error.status = xhr.status;
          reject(error);
        }
      });

      xhr.addEventListener('error', () => {
        reject(new Error('Network error during upload'));
      });

      xhr.addEventListener('abort', () => {
        reject(new DOMException('Upload aborted', 'AbortError'));
      });

      // Get the base URL and token
      const baseUrl = api.defaults?.baseURL || '';
      const authToken = token || api.defaults?.headers?.common?.Authorization?.replace('Bearer ', '');
      
      xhr.open('POST', `${baseUrl}/api/media/upload/${category}`);
      if (authToken) {
        xhr.setRequestHeader('Authorization', `Bearer ${authToken}`);
      }
      
      xhr.send(formData);
    });
  }
}

