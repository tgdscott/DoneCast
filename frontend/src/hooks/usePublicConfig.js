import { useCallback, useEffect, useState } from 'react';

let cachedConfig = null;
let inflightPromise = null;

const fetchConfig = async () => {
  const response = await fetch('/api/public/config', { credentials: 'include' });
  if (!response.ok) {
    const error = new Error(`Failed to load public config (${response.status})`);
    error.status = response.status;
    throw error;
  }
  const data = await response.json();
  cachedConfig = data ?? null;
  return cachedConfig;
};

export const loadPublicConfig = async ({ force } = {}) => {
  if (cachedConfig && !force) {
    return cachedConfig;
  }
  if (inflightPromise) {
    return inflightPromise;
  }
  inflightPromise = fetchConfig()
    .catch((error) => {
      cachedConfig = null;
      throw error;
    })
    .finally(() => {
      inflightPromise = null;
    });
  return inflightPromise;
};

export const resetPublicConfigCache = () => {
  cachedConfig = null;
  inflightPromise = null;
};

export default function usePublicConfig() {
  const [config, setConfig] = useState(cachedConfig);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(!cachedConfig);

  const refresh = useCallback(async ({ force } = {}) => {
    setLoading(true);
    try {
      const data = await loadPublicConfig({ force: force !== false });
      setConfig(data);
      setError(null);
      return data;
    } catch (err) {
      setError(err);
      setConfig(null);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let isMounted = true;
    if (!cachedConfig) {
      loadPublicConfig()
        .then((data) => {
          if (!isMounted) return;
          setConfig(data);
          setError(null);
          setLoading(false);
        })
        .catch((err) => {
          if (!isMounted) return;
          setError(err);
          setConfig(null);
          setLoading(false);
        });
    } else {
      setConfig(cachedConfig);
      setLoading(false);
    }
    return () => {
      isMounted = false;
    };
  }, []);

  return { config, error, loading, refresh };
}
