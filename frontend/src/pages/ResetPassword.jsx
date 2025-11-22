import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { buildApiUrl } from '@/lib/apiClient.js';
import { useAuth } from '@/AuthContext.jsx';

const apiUrl = (path) => buildApiUrl(path);

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { login } = useAuth();
  const token = searchParams.get('token');
  
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const passwordRef = useRef(null);
  const confirmPasswordRef = useRef(null);

  useEffect(() => {
    if (!token) {
      setError('Invalid reset link. Please request a new password reset.');
    }
  }, [token]);

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

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    
    if (!token) {
      setError('Invalid reset link. Please request a new password reset.');
      return;
    }

    if (!password) {
      setError('Password is required.');
      passwordRef.current?.focus();
      return;
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters long.');
      passwordRef.current?.focus();
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      confirmPasswordRef.current?.focus();
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch(apiUrl('/api/auth/reset-password'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token,
          new_password: password,
        }),
        credentials: 'include',
      });

      const data = await res.json().catch(() => ({}));
      
      if (!res.ok) {
        const errorMsg = normalizeMessage(
          data?.detail || data?.message,
          'Failed to reset password. The link may have expired. Please request a new one.'
        );
        setError(errorMsg);
        return;
      }

      setSuccess(true);
      // Auto-login after successful password reset
      setTimeout(async () => {
        try {
          // Try to get user email from the reset token (we'll need to fetch it)
          // For now, redirect to login - user can sign in with new password
          navigate('/?login=1');
        } catch (err) {
          navigate('/?login=1');
        }
      }, 2000);
    } catch (err) {
      setError('An unexpected error occurred. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Invalid Reset Link</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-4">
              This password reset link is invalid or has expired. Please request a new password reset.
            </p>
            <Button onClick={() => navigate('/?login=1')} className="w-full">
              Go to Sign In
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Password Reset Successful</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-4">
              Your password has been reset successfully. Redirecting to sign in...
            </p>
            <Button onClick={() => navigate('/?login=1')} className="w-full">
              Go to Sign In
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Reset Your Password</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div
                className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
                role="alert"
                aria-live="assertive"
              >
                {error}
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="password">New Password</Label>
              <div className="relative">
                <Input
                  ref={passwordRef}
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="pr-20"
                  placeholder="Enter new password"
                  disabled={submitting}
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
              <p className="text-xs text-muted-foreground">
                Password must be at least 8 characters long.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirmPassword">Confirm Password</Label>
              <div className="relative">
                <Input
                  ref={confirmPasswordRef}
                  id="confirmPassword"
                  type={showConfirmPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="pr-20"
                  placeholder="Confirm new password"
                  disabled={submitting}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="absolute inset-y-1 right-1 h-7 px-2 text-xs"
                  onClick={() => setShowConfirmPassword((prev) => !prev)}
                  aria-pressed={showConfirmPassword}
                  aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
                >
                  {showConfirmPassword ? 'Hide' : 'Show'}
                </Button>
              </div>
            </div>
            <Button type="submit" className="w-full" disabled={submitting || !password || !confirmPassword}>
              {submitting ? 'Resetting Password…' : 'Reset Password'}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => navigate('/?login=1')}
              className="w-full"
              disabled={submitting}
            >
              Back to Sign In
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}




