import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Mail, CheckCircle2, AlertCircle } from 'lucide-react';

/**
 * EmailVerification page - standalone, no navigation escape.
 * Users must enter a 6-digit code or click the link from their email.
 */
export default function EmailVerification() {
  const navigate = useNavigate();
  const location = useLocation();
  
  // Get email and password from sessionStorage (set during registration)
  const storedEmail = sessionStorage.getItem('pendingVerificationEmail') || '';
  const storedPassword = sessionStorage.getItem('pendingVerificationPassword') || '';
  
  const [email, setEmail] = useState(location.state?.email || storedEmail);
  const [code, setCode] = useState('');
  const [password, setPassword] = useState(location.state?.password || storedPassword);
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [expiresAt, setExpiresAt] = useState(Date.now() + 15 * 60 * 1000);

  // Calculate remaining time
  const [remainingMinutes, setRemainingMinutes] = useState(15);
  
  useEffect(() => {
    // Redirect to home if no email is present
    if (!email) {
      navigate('/', { replace: true });
      return;
    }
    
    const interval = setInterval(() => {
      const remaining = Math.max(0, Math.floor((expiresAt - Date.now()) / 60000));
      setRemainingMinutes(remaining);
    }, 1000);
    return () => clearInterval(interval);
  }, [expiresAt, email, navigate]);

  const handleVerifyCode = async (e) => {
    e.preventDefault();
    if (code.length !== 6) {
      setError('Please enter the complete 6-digit code.');
      return;
    }

    setError('');
    setIsSubmitting(true);

    try {
      // Step 1: Verify the code
      const verifyRes = await fetch('/api/auth/confirm-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, code }),
        credentials: 'include',
      });

      if (!verifyRes.ok) {
        const data = await verifyRes.json().catch(() => ({}));
        setError(data?.detail || 'Invalid or expired code. Please check and try again.');
        setIsSubmitting(false);
        return;
      }

      // Step 2: Log them in automatically if we have the password
      if (password) {
        const formData = new URLSearchParams();
        formData.append('username', email);
        formData.append('password', password);

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
            // Redirect to root with verified flag - let App.jsx route to onboarding
            window.location.href = '/?verified=1';
            return;
          }
        }
      }

      // If auto-login failed or no password, clean up and redirect
      sessionStorage.removeItem('pendingVerificationEmail');
      sessionStorage.removeItem('pendingVerificationPassword');
      // Redirect to home with verified flag so onboarding triggers after they log in
      window.location.href = '/?verified=1&login=1';
    } catch (err) {
      setError('Network error. Please check your connection and try again.');
      setIsSubmitting(false);
    }
  };

  const handleResendCode = async () => {
    if (isResending) return;
    
    setError('');
    setIsResending(true);

    try {
      const res = await fetch('/api/auth/resend-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });

      if (res.ok) {
        setExpiresAt(Date.now() + 15 * 60 * 1000);
        setCode('');
        setError(''); // Clear any existing errors
        // Show success in a non-error way
        setTimeout(() => {
          setError(''); // Make sure error stays clear
        }, 100);
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data?.detail || 'Failed to resend code. Please try again.');
      }
    } catch (err) {
      setError('Network error. Could not resend code.');
    } finally {
      setIsResending(false);
    }
  };

  const minutesText = remainingMinutes === 1 ? '1 minute' : `${remainingMinutes} minutes`;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex items-center justify-center p-4">
      <Card className="w-full max-w-md shadow-lg">
        <CardHeader className="text-center space-y-2 pb-6">
          <div className="flex justify-center mb-2">
            <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center">
              <Mail className="w-8 h-8 text-blue-600" />
            </div>
          </div>
          <CardTitle className="text-2xl">Verify Your Email</CardTitle>
          <p className="text-sm text-muted-foreground">
            We've sent a 6-digit verification code to
          </p>
          <p className="text-sm font-semibold text-foreground">{email}</p>
        </CardHeader>
        
        <CardContent className="space-y-6">
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-900">
            <p className="flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>
                Enter the 6-digit code below or click the link in the email to complete your registration.
                {remainingMinutes > 0 && (
                  <span className="block mt-1 text-blue-700">
                    Code expires in {minutesText}.
                  </span>
                )}
              </span>
            </p>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-900">
              <p className="flex items-start gap-2">
                <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                <span>{error}</span>
              </p>
            </div>
          )}

          <form onSubmit={handleVerifyCode} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="code" className="text-base">
                Verification Code
              </Label>
              <Input
                id="code"
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/[^0-9]/g, ''))}
                placeholder="000000"
                className="text-center text-2xl tracking-widest font-mono"
                autoFocus
                disabled={isSubmitting}
              />
              <p className="text-xs text-muted-foreground text-center">
                Enter the code from your email
              </p>
            </div>

            <Button
              type="submit"
              className="w-full"
              disabled={code.length !== 6 || isSubmitting}
              size="lg"
            >
              {isSubmitting ? 'Verifying...' : 'Verify Email'}
            </Button>
          </form>

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-200"></div>
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-white px-2 text-muted-foreground">
                Didn't receive the code?
              </span>
            </div>
          </div>

          <Button
            type="button"
            variant="outline"
            className="w-full"
            onClick={handleResendCode}
            disabled={isResending}
          >
            {isResending ? 'Sending...' : 'Resend Code'}
          </Button>

          <div className="text-center">
            <p className="text-xs text-muted-foreground">
              Check your spam folder if you don't see the email.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
