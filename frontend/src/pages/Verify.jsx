import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

export default function Verify() {
  const [status, setStatus] = useState('idle'); // idle|verifying|success|error
  const [message, setMessage] = useState('');
  const navigate = useNavigate();

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
          setMessage(data?.detail || data?.message || 'Verification failed or expired.');
          return;
        }
        setStatus('success');
        setMessage('Your email has been confirmed. You can continue onboarding.');
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
                <Button onClick={() => navigate('/onboarding')}>Continue</Button>
                <Button variant="outline" onClick={() => navigate('/')}>Home</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
