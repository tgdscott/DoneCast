import React, { createContext, useState, useContext, useEffect, useCallback, useRef } from 'react';
import { makeApi } from './lib/apiClient';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [token, setToken] = useState(() => {
        try { return localStorage.getItem('authToken'); } catch { return null; }
    });
    const [user, setUser] = useState(null);
    const [backendOnline, setBackendOnline] = useState(true);
    const [hydrated, setHydrated] = useState(false); // whether we've successfully attempted to load /me

    const refreshInFlight = useRef(false);
    const errorCountRef = useRef(0);
    const lastAttemptRef = useRef(0);
    const backoffRef = useRef(2000); // start at 2s
    const maxBackoff = 60000; // 60s cap

    useEffect(() => {
        try {
            if (token) {
                localStorage.setItem('authToken', token);
            } else {
                localStorage.removeItem('authToken');
            }
        } catch (e) {
            // ignore storage failures
        }
    }, [token]);

    const login = (newToken) => {
        setToken(newToken);
    };

    const logout = () => {
        setToken(null);
        setUser(null);
        setHydrated(true);
    };

    const refreshUser = useCallback(async (opts={ force:false }) => {
        // If no token present, ensure user cleared and mark hydrated
        if(!token) { setUser(null); setHydrated(true); return; }
        const now = Date.now();
        // Respect cooldown when backend offline unless force
        if(!opts.force && !backendOnline) {
            const since = now - lastAttemptRef.current;
            if(since < backoffRef.current) {
                return; // skip due to backoff
            }
        }
        if(refreshInFlight.current && !opts.force) return;
        refreshInFlight.current = true;
        lastAttemptRef.current = now;
        try {
            const api = makeApi(token);
            const data = await api.get('/api/users/me');
            // data should be JSON user object
            setUser(data);
            setBackendOnline(true);
            errorCountRef.current = 0;
            backoffRef.current = 2000; // reset backoff
            setHydrated(true);
        } catch(err) {
            // Only clear token on explicit 401 Unauthorized
            if(err && err.status === 401) {
                setUser(null);
                setToken(null);
                setHydrated(true);
                return;
            }
            // non-auth failures: mark backend offline and backoff
            if(backendOnline) setBackendOnline(false);
            errorCountRef.current += 1;
            backoffRef.current = Math.min(backoffRef.current * 2, maxBackoff);
            // keep hydrated true to allow UI to continue (we attempted)
            setHydrated(true);
        } finally {
            refreshInFlight.current = false;
        }
    }, [token, backendOnline]);

    useEffect(()=>{ refreshUser(); }, [token, refreshUser]);

    // React to hash capture event (in case provider code fires after initial render)
    useEffect(() => {
        function onCaptured(e) {
            const t = e.detail && e.detail.token;
            if(t && t !== token) {
                setToken(t);
            }
        }
        window.addEventListener('ppp-token-captured', onCaptured);
        return () => window.removeEventListener('ppp-token-captured', onCaptured);
    }, [token]);

    const acceptTerms = useCallback(async (version) => {
        if (!token) throw new Error('Not authenticated');
        const api = makeApi(token);
        const data = await api.post('/api/auth/terms/accept', { version });
        // Server returns updated UserPublic; update local state
        setUser(data);
        return data;
    }, [token]);

    const value = { token, user, login, logout, refreshUser, isAuthenticated: !!token, backendOnline, hydrated, acceptTerms };

    return (
        <AuthContext.Provider value={value}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => {
    return useContext(AuthContext);
};
