import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

export default function Verify() {
  const [status, setStatus] = useState('idle'); // idle|verifying|success|error
  const [message, setMessage] = useState('');
  const navigate = useNavigate();

  const normalizeMessage = (value, fallback) => {
    if (value == null || value === '') return fallback;
    if (typeof value === 'string') return value;
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

  useEffect(() => {
    const run = async () => {
      const params = new URLSearchParams(window.location.search);
      const token = params.get('token') || '';
      const email = params.get('email') || '';
      if (!token && !email) {
        setStatus('error');
        setMessage('Missing verification token. Please open the link from your email.');
        return;
      }
      setStatus('verifying');
      try {
        const res = await fetch('/api/auth/confirm-email', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token, email }),
          credentials: 'include',
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          setStatus('error');
          setMessage(
            normalizeMessage(
              (data && data.detail) || (data && data.message),
              'Verification failed or expired.'
            )
          );
          return;
        }
        
        const verificationData = await res.json();
        
        // If backend returned an access token (when verifying via token link), use it to auto-login
        if (verificationData.access_token) {
          try {
            // Store token
            localStorage.setItem('authToken', verificationData.access_token);
            
            // CRITICAL: Pre-fetch user data to ensure AuthContext has fresh data
            // This prevents race condition where App.jsx renders with stale/null user
            try {
              const userRes = await fetch('/api/users/me', {
                headers: { 'Authorization': `Bearer ${verificationData.access_token}` }
              });
              if (userRes.ok) {
                const userData = await userRes.json();
                console.log('[Verify] User verified and active:', userData.is_active);
              }
            } catch (err) {
              console.warn('[Verify] Could not pre-fetch user data (will retry):', err);
            }
            
            // Clean up any stored credentials
            sessionStorage.removeItem('pendingVerificationEmail');
            sessionStorage.removeItem('pendingVerificationPassword');
            
            // Redirect to root with verified flag - let App.jsx handle routing
            // This ensures new users go through onboarding
            window.location.href = '/?verified=1';
            return;
          } catch (loginErr) {
            console.error('Auto-login failed:', loginErr);
            // Fall through to manual login prompt
          }
        }
        
        // Fallback: Try auto-login with stored credentials (for code-based verification)
        const storedEmail = sessionStorage.getItem('pendingVerificationEmail');
        const storedPassword = sessionStorage.getItem('pendingVerificationPassword');
        
        if (storedEmail && storedPassword) {
          try {
            // Auto-login the user
            const formData = new URLSearchParams();
            formData.append('username', storedEmail);
            formData.append('password', storedPassword);

            const loginRes = await fetch('/api/auth/token', {
              method: 'POST',
              headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
              body: formData.toString(),
              credentials: 'include',
            });

            if (loginRes.ok) {
              const data = await loginRes.json();
              if (data.access_token) {
                // Clean up stored credentials
                sessionStorage.removeItem('pendingVerificationEmail');
                sessionStorage.removeItem('pendingVerificationPassword');
                // Store token
                localStorage.setItem('authToken', data.access_token);
                
                // CRITICAL: Pre-fetch user data to ensure AuthContext has fresh data
                try {
                  const userRes = await fetch('/api/users/me', {
                    headers: { 'Authorization': `Bearer ${data.access_token}` }
                  });
                  if (userRes.ok) {
                    const userData = await userRes.json();
                    console.log('[Verify] User verified and active:', userData.is_active);
                  }
                } catch (err) {
                  console.warn('[Verify] Could not pre-fetch user data (will retry):', err);
                }
                
                // Redirect to root with onboarding flag
                window.location.href = '/?verified=1';
                return;
              }
            }
          } catch (loginErr) {
            console.error('Auto-login failed:', loginErr);
            // Fall through to manual login prompt
          }
        }
        
        // If auto-login didn't work, show success message and prompt manual login
        sessionStorage.removeItem('pendingVerificationEmail');
        sessionStorage.removeItem('pendingVerificationPassword');
        setStatus('success');
        setMessage('Your email has been confirmed! Please log in to continue.');
      } catch (e) {
        setStatus('error');
        setMessage('Verification request failed. Check your connection and try again.');
      }
    };
    run();
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Email Verification</CardTitle>
        </CardHeader>
        <CardContent>
          {status === 'verifying' && <div>Verifying…</div>}
          {status !== 'verifying' && (
            <div className="space-y-4">
              <div className={status === 'success' ? 'text-emerald-700' : 'text-red-700'}>{message}</div>
              <div className="flex gap-2">
                {status === 'success' ? (
                  <Button onClick={() => navigate('/?login=1')}>Log In to Continue</Button>
                ) : (
                  <Button onClick={() => navigate('/')}>Go Home</Button>
                )}
                <Button variant="outline" onClick={() => navigate('/')}>Home</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
