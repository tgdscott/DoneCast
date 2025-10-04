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
      if (!event.lengthComputable) {
        onProgress({ loaded: event.loaded, total: event.total, percent: null });
        return;
      }
      const percent = event.total > 0 ? Math.min(100, Math.round((event.loaded / event.total) * 100)) : null;
      onProgress({ loaded: event.loaded, total: event.total, percent });
    };

    xhr.onerror = () => {
      reject(new Error('Upload failed. Please try again.'));
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
      const message = `Upload failed with status ${xhr.status}`;
      reject(new Error(message));
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

  const presign = await api.post(`/api/media/upload/${category}/presign`, {
    filename: file.name || 'upload',
    content_type: contentType,
  });

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
}

