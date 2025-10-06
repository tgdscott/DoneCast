import { useState, useEffect, useRef, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import GoogleSignInButton from '@/components/GoogleSignInButton';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/AuthContext.jsx';
import { buildApiUrl } from '@/lib/apiClient.js';
import { X } from 'lucide-react';

const apiUrl = (path) => buildApiUrl(path);

const buildGoogleLoginUrl = () => {
  // Start with buildApiUrl so production / non-proxied environments work seamlessly.
  let url = buildApiUrl('/api/auth/login/google') || '/api/auth/login/google';

  // If buildApiUrl returned a relative path (dev proxy case), decide whether to
  // upgrade to an absolute API origin to avoid redirect_uri mismatches.
  const isAbsolute = /^https?:\/\//i.test(url);
  if (!isAbsolute) {
    if (!url.startsWith('/')) url = `/${url}`;
    if (typeof window !== 'undefined') {
      const loc = window.location;
      const host = (loc && loc.host) || '';
      // When running the frontend dev server (port 5173), Google console usually has
      // callback configured for backend port 8000. Force absolute API origin so
      // Google's redirect_uri matches what FastAPI reports.
      if (/^127\.0\.0\.1:5173$/.test(host) || /^localhost:5173$/.test(host)) {
        // Use same protocol (normally http in local dev)
        const proto = (loc && loc.protocol) || 'http:';
        url = `${proto}//127.0.0.1:8000${url}`;
      }
    }
  }

  if (typeof window !== 'undefined') {
    const loc = window.location;
    const origin = loc?.origin ? loc.origin.replace(/\/+$/, '') : '';
    // Preserve current path (without hash) so post-OAuth flow can land where user began.
    const rawPath = (loc?.pathname || '/') + (loc?.search || '');
    // Basic sanitization: limit length & ensure leading slash
    let cleanedPath = rawPath.startsWith('/') ? rawPath : `/${rawPath}`;
    if (cleanedPath.length > 512) cleanedPath = cleanedPath.slice(0, 512);
    if (origin) {
      const sep = url.includes('?') ? '&' : '?';
      url = `${url}${sep}return_to=${encodeURIComponent(origin)}&return_path=${encodeURIComponent(cleanedPath)}`;
    }
  }
  return url;
};

const normalizeMessage = (value, fallback) => {
  if (value == null || value === '') {
    return fallback;
  }
  if (typeof value === 'string') {
    return value;
  }
  if (Array.isArray(value)) {
    const joined = value
      .map((item) => {
        if (!item) return '';
        if (typeof item === 'string') return item;
        if (item?.msg) {
          const loc = Array.isArray(item.loc) ? item.loc.join('.') : item.loc;
          return loc ? `${item.msg} (${loc})` : item.msg;
        }
        try {
          return JSON.stringify(item);
        } catch (err) {
          return String(item);
        }
      })
      .filter(Boolean)
      .join(' ');
    return joined || fallback;
  }
  if (typeof value === 'object') {
    if (value.detail && value.detail !== value) {
      return normalizeMessage(value.detail, fallback);
    }
    if (value.message && value.message !== value) {
      return normalizeMessage(value.message, fallback);
    }
    try {
      const serialized = JSON.stringify(value);
      if (serialized && serialized !== '{}') {
        return serialized;
      }
    } catch (err) {
      return fallback;
    }
  }
  return String(value) || fallback;
};

export default function LoginModal({ onClose }) {
  const { login } = useAuth();
  const googleLoginUrl = useMemo(buildGoogleLoginUrl, []);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [errorTone, setErrorTone] = useState('error');
  const [mode, setMode] = useState('login'); // 'login' | 'register' | 'verify'
  const [verifyCode, setVerifyCode] = useState('');
  const [verificationEmail, setVerificationEmail] = useState('');
  const [verifyExpiresAt, setVerifyExpiresAt] = useState(null); // timestamp ms
  const [resendPending, setResendPending] = useState(false);
  const [changeEmail, setChangeEmail] = useState(false);
  const [newEmail, setNewEmail] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const emailRef = useRef(null);
  const passwordRef = useRef(null);
  const fallbackTermsVersion = import.meta?.env?.VITE_TERMS_VERSION || '2025-09-19';
  const [termsInfo, setTermsInfo] = useState({ version: fallbackTermsVersion, url: '/terms' });
  const [termsLoading, setTermsLoading] = useState(false);
  const [registerSubmitting, setRegisterSubmitting] = useState(false);

  const showError = (message, tone = 'error') => {
    setError(message);
    setErrorTone(tone);
  };

  const clearError = () => {
    setError('');
    setErrorTone('error');
  };

  useEffect(() => {
    let cancelled = false;
    const loadTerms = async () => {
      setTermsLoading(true);
      try {
        const res = await fetch(apiUrl('/api/auth/terms/info'));
        if (!res.ok) {
          throw new Error('terms_fetch_failed');
        }
        const data = await res.json().catch(() => ({}));
        if (!cancelled) {
          setTermsInfo({
            version: (data && data.version) || fallbackTermsVersion,
            url: (data && data.url) || '/terms',
          });
        }
      } catch (_err) {
        if (!cancelled) {
          setTermsInfo((prev) => ({
            version: (prev && prev.version) || fallbackTermsVersion,
            url: (prev && prev.url) || '/terms',
          }));
        }
      } finally {
        if (!cancelled) {
          setTermsLoading(false);
        }
      }
    };
    loadTerms();
    return () => {
      cancelled = true;
    };
  }, [fallbackTermsVersion]);

  const attemptEmailLogin = async (nextEmail, nextPassword) => {
    const params = new URLSearchParams({
      username: (nextEmail ?? email).trim(),
      password: nextPassword ?? password,
    });
    try {
      const res = await fetch(apiUrl('/api/auth/token'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: params.toString(),
        credentials: 'include',
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data && data.access_token) {
        login(data.access_token);
        onClose?.();
        return;
      }
      if (res.status === 401) {
        const detail = normalizeMessage(
          data?.detail || data?.message,
          'Invalid email or password.'
        );
        if (/confirm your email/i.test(detail)) {
          showError(detail, 'info');
        } else {
          showError(detail, 'error');
        }
      } else {
        showError(
          normalizeMessage(
            data?.detail || data?.message,
            'An unexpected error occurred. Please try again.'
          )
        );
      }
      throw new Error('login_failed');
    } catch (err) {
      if (err.message !== 'login_failed') {
        showError('An unexpected error occurred. Please try again.');
      }
      throw err;
    }
  };

  const ensureFields = () => {
    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      showError('Email is required.');
      emailRef.current?.focus();
      return null;
    }
    if (!password) {
      showError('Password is required.');
      passwordRef.current?.focus();
      return null;
    }
    return trimmedEmail;
  };

  const handleEmailLogin = async (e) => {
    e.preventDefault();
    clearError();
    const trimmedEmail = ensureFields();
    if (!trimmedEmail) return;
    setEmail(trimmedEmail);
    try {
      await attemptEmailLogin(trimmedEmail, password);
    } catch (_) {
      // error already surfaced via setError
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    clearError();
    const trimmedEmail = ensureFields();
    if (!trimmedEmail) return;
    setEmail(trimmedEmail);
    const versionToSend = termsInfo?.version || fallbackTermsVersion;
    setRegisterSubmitting(true);
    let encounteredError = false;
    try {
      const res = await fetch(apiUrl('/api/auth/register'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: trimmedEmail,
          password,
          accept_terms: true,
          terms_version: versionToSend,
        }),
        credentials: 'include',
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        encounteredError = true;
        if (res.status === 400) {
          showError(
            normalizeMessage(
              data?.detail || data?.message,
              'A user with this email already exists.'
            )
          );
        } else {
          showError(
            normalizeMessage(
              data?.detail || data?.message,
              'Registration failed. Please try again.'
            )
          );
        }
        return;
      }
      const data = await res.json().catch(() => ({}));
      const inactive = Boolean(data?.detail?.includes?.('inactive')) || data?.requires_verification;
      if (inactive) {
        setVerificationEmail(trimmedEmail);
        setVerifyExpiresAt(Date.now() + 15 * 60 * 1000);
        setMode('verify');
        setVerifyCode('');
        setChangeEmail(false);
        setNewEmail('');
        return;
      }
      await attemptEmailLogin(trimmedEmail, password);
    } catch (err) {
      if (!encounteredError) {
        showError('Registration error. Please try again.');
      }
    } finally {
      setRegisterSubmitting(false);
    }
  };

  const submitDisabled =
    mode === 'login'
      ? !email.trim() || !password
      : mode === 'register'
        ? registerSubmitting || !email.trim() || !password
        : false;

  const submitText =
    mode === 'login' ? 'Sign In' : registerSubmitting ? 'Creating…' : 'Create Account';

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <Card className="w-full max-w-md mx-4">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>{mode === 'login' ? 'Sign In' : 'Create Account'}</CardTitle>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="w-4 h-4" />
          </Button>
        </CardHeader>
        <CardContent>
          {mode !== 'verify' && (
            <form onSubmit={mode === 'login' ? handleEmailLogin : handleRegister} className="space-y-4">
              {error && (
                <div
                  className={`rounded-md border px-3 py-2 text-sm ${
                    errorTone === 'info'
                      ? 'border-blue-200 bg-blue-50 text-blue-700'
                      : errorTone === 'success'
                        ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                        : 'border-red-200 bg-red-50 text-red-700'
                  }`}
                  role="alert"
                  aria-live="assertive"
                >
                  {error}
                </div>
              )}
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  ref={emailRef}
                  id="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  inputMode="email"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Input
                    ref={passwordRef}
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="pr-20"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="absolute inset-y-1 right-1 h-7 px-2 text-xs"
                    onClick={() => setShowPassword((prev) => !prev)}
                    aria-pressed={showPassword}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? 'Hide' : 'Show'}
                  </Button>
                </div>
              </div>
              <Button type="submit" className="w-full" disabled={submitDisabled}>
                {submitText}
              </Button>
              <button
                type="button"
                onClick={() => {
                  setMode((m) => (m === 'login' ? 'register' : 'login'));
                  clearError();
                  setRegisterSubmitting(false);
                }}
                className="w-full text-xs text-blue-600 hover:underline"
              >
                {mode === 'login' ? 'Need an account? Sign up' : 'Have an account? Sign in'}
              </button>
            </form>
          )}
          {mode === 'verify' && (
            <div className="space-y-4" data-state="verify-flow">
              <div className="text-sm text-muted-foreground">
                We sent a 6‑digit code to <strong>{verificationEmail}</strong>. Enter it below or click the link in the email. This code expires in {verifyExpiresAt ? Math.max(0, Math.floor((verifyExpiresAt - Date.now()) / 60000)) : 15}m.
              </div>
              <div className="space-y-2">
                <Label htmlFor="verifyCode">Verification Code</Label>
                <Input
                  id="verifyCode"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  value={verifyCode}
                  autoFocus
                  onChange={(e) => setVerifyCode(e.target.value.replace(/[^0-9]/g, ''))}
                  placeholder="123456"
                  className="tracking-widest text-center text-lg"
                />
              </div>
              <div className="flex gap-2">
                <Button
                  disabled={verifyCode.length !== 6}
                  onClick={async () => {
                    clearError();
                    try {
                      const res = await fetch(apiUrl('/api/auth/confirm-email'), {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ email: verificationEmail, code: verifyCode }),
                        credentials: 'include',
                      });
                      const data = await res.json().catch(() => ({}));
                      if (!res.ok) {
                        showError(normalizeMessage(data?.detail || data?.message, 'Invalid or expired code.'));
                        return;
                      }
                      try {
                        await attemptEmailLogin(verificationEmail, password);
                      } catch {}
                    } catch (err) {
                      showError('Verification failed.');
                    }
                  }}
                >
                  Confirm
                </Button>
                <Button
                  variant="outline"
                  onClick={async () => {
                    clearError();
                    if (resendPending) return;
                    setResendPending(true);
                    try {
                      await fetch(apiUrl('/api/auth/resend-verification'), {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ email: verificationEmail }),
                      });
                      setVerifyExpiresAt(Date.now() + 15 * 60 * 1000);
                      showError('New code sent (check spam folder if not visible).', 'info');
                    } catch {}
                    setResendPending(false);
                  }}
                >
                  Resend
                </Button>
                <Button variant="ghost" onClick={() => {
                  setMode('login');
                  clearError();
                }}>
                  Cancel
                </Button>
              </div>
              <div className="space-y-2">
                {!changeEmail && (
                  <button
                    className="text-xs text-blue-600 hover:underline"
                    type="button"
                    onClick={() => {
                      setChangeEmail(true);
                      setNewEmail(verificationEmail);
                    }}
                  >
                    Wrong email? Change it
                  </button>
                )}
                {changeEmail && (
                  <div className="space-y-2 border rounded p-3">
                    <Label htmlFor="newEmail">New Email</Label>
                    <Input
                      id="newEmail"
                      type="email"
                      value={newEmail}
                      onChange={(e) => setNewEmail(e.target.value)}
                    />
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        disabled={!newEmail.trim() || newEmail === verificationEmail}
                        onClick={async () => {
                          clearError();
                          try {
                            const res = await fetch(apiUrl('/api/auth/update-pending-email'), {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({ old_email: verificationEmail, new_email: newEmail.trim() }),
                            });
                            if (!res.ok) {
                              const d = await res.json().catch(() => ({}));
                              showError(normalizeMessage(d?.detail || d?.message, 'Unable to update email.'));
                              return;
                            }
                            setVerificationEmail(newEmail.trim());
                            setVerifyExpiresAt(Date.now() + 15 * 60 * 1000);
                            setVerifyCode('');
                            setChangeEmail(false);
                            showError('Email updated. New code sent.', 'info');
                          } catch {
                            showError('Update failed');
                          }
                        }}
                      >
                        Save
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => {
                        setChangeEmail(false);
                      }}>
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
          {mode !== 'verify' && (
            <div className="relative my-4">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-white px-2 text-muted-foreground">Or continue with</span>
              </div>
            </div>
          )}
          {mode !== 'verify' && <GoogleSignInButton href={googleLoginUrl} />}
        </CardContent>
      </Card>
    </div>
  );
}
