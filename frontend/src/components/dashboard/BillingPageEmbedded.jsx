import { useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '@/AuthContext';
import { useToast } from '@/hooks/use-toast';
import { Button } from '../ui/button';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/card';
import { Progress } from '../ui/progress';
import { Badge } from '@/components/ui/badge';
import { makeApi, isApiError } from '@/lib/apiClient';
import { useResolvedTimezone } from '@/hooks/useResolvedTimezone';
import { formatToPartsInTimezone } from '@/lib/timezone';
import { loadStripe } from '@stripe/stripe-js';
import {
  EmbeddedCheckoutProvider,
  EmbeddedCheckout,
} from '@stripe/react-stripe-js';

export default function BillingPageEmbedded({ token, onBack }) {
  const { refreshUser } = useAuth();
  const resolvedTimezone = useResolvedTimezone();
  const [subscription, setSubscription] = useState(null);
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [portalLoading, setPortalLoading] = useState(false);
  const [annual, setAnnual] = useState(false);
  const [stripePromise, setStripePromise] = useState(null);
  const [clientSecret, setClientSecret] = useState(null);
  const [showCheckout, setShowCheckout] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const { toast } = (() => { try { return useToast(); } catch { return { toast: () => {} }; } })();
  
  // Initialize Stripe
  useEffect(() => {
    const initStripe = async () => {
      try {
        const api = makeApi(token);
        const config = await api.get('/api/billing/config');
        const stripe = await loadStripe(config.publishable_key);
        setStripePromise(stripe);
      } catch (e) {
        console.error('Failed to initialize Stripe:', e);
        const msg = isApiError(e) ? (e.detail || e.error || e.message) : String(e);
        setError(msg);
      }
    };
    initStripe();
  }, [token]);

  const fetchAll = async () => {
    try {
      const api = makeApi(token);
      const [subData, usageData] = await Promise.all([
        api.get('/api/billing/subscription'),
        api.get('/api/billing/usage'),
      ]);
      setSubscription(subData);
      setUsage(usageData);
    } catch (e) {
      const msg = isApiError(e) ? (e.detail || e.error || e.message) : String(e);
      setError(msg);
    }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchAll(); }, [token]);

  // Handle coming back from checkout
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const isSuccess = params.get('checkout') === 'success';
    const sessionId = params.get('session_id');
    
    if (!isSuccess) return;
    
    (async () => {
      try {
        toast({ 
          title: 'Processing Purchase', 
          description: 'Finalizing your subscription...', 
          duration: 4000 
        });
      } catch {}
      
      // Attempt immediate force sync
      let upgraded = false;
      if (sessionId) {
        for (let attempt = 0; attempt < 6 && !upgraded; attempt++) {
          try {
            const api = makeApi(token);
            const fsData = await api.post('/api/billing/force_sync_session', { session_id: sessionId });
            if (fsData?.plan_key && fsData.plan_key !== 'free') {
              setSubscription(s => ({ 
                ...(s || {}), 
                plan_key: fsData.plan_key, 
                current_period_end: fsData.current_period_end 
              }));
              upgraded = true;
              refreshUser({ force: true });
              setTimeout(() => refreshUser({ force: true }), 1200);
              toast({ 
                title: 'Subscription Upgraded', 
                description: `You are now on the ${fsData.plan_key} plan.`, 
                duration: 5000 
              });
            }
          } catch {}
          if (!upgraded) await new Promise(res => setTimeout(res, 800));
        }
      }
      
      fetchAll();
      try { 
        window.history.replaceState(null, '', window.location.pathname); 
      } catch {}
    })();
  }, [token, toast]);

  const startEmbeddedCheckout = async (planKey, billingCycle = 'monthly') => {
    try {
      setSelectedPlan({ key: planKey, cycle: billingCycle });
      const api = makeApi(token);
      const data = await api.post('/api/billing/checkout/embedded', { 
        plan_key: planKey, 
        billing_cycle: billingCycle,
        success_path: '/billing',
        cancel_path: '/billing'
      });
      setClientSecret(data.client_secret);
      setShowCheckout(true);
    } catch (e) {
      const msg = isApiError(e) ? (e.detail || e.error || e.message) : String(e);
      setError(msg);
      toast({ 
        title: 'Checkout Error', 
        description: msg, 
        variant: 'destructive',
        duration: 5000 
      });
    }
  };

  const openPortal = async () => {
    try {
      setPortalLoading(true);
      const api = makeApi(token);
      const data = await api.post('/api/billing/portal', {});
      window.location.href = data.url;
    } catch (e) {
      const msg = isApiError(e) ? (e.detail || e.error || e.message) : String(e);
      setError(msg);
    }
    finally { setPortalLoading(false); }
  };

  const formatDate = (iso) => {
    const parts = formatToPartsInTimezone(iso, { month: '2-digit', day: '2-digit', year: 'numeric' }, resolvedTimezone);
    if (!parts) return iso;
    const lookup = parts.reduce((acc, part) => {
      if (part.type === 'month' || part.type === 'day' || part.type === 'year') {
        acc[part.type] = part.value;
      }
      return acc;
    }, {});
    if (lookup.month && lookup.day && lookup.year) {
      return `${lookup.month}-${lookup.day}-${lookup.year}`;
    }
    return iso;
  };

  // Pricing data
  const tiers = useMemo(() => ([
    {
      key: 'pro',
      name: 'Pro',
      monthly: 19,
      annual: 190,
      features: [
        'Unlimited episodes',
        'Advanced AI enhancement',
        'Priority processing',
        'Custom branding',
        'Analytics dashboard'
      ]
    },
    {
      key: 'creator',
      name: 'Creator',
      monthly: 49,
      annual: 490,
      features: [
        'Everything in Pro',
        'Unlimited processing minutes',
        'Custom AI voice training',
        'White-label options',
        'Dedicated support',
        'API access'
      ]
    }
  ]), []);

  const currentTier = subscription?.plan_key || 'free';
  const isSubscribed = currentTier !== 'free';

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading billing information...</p>
        </div>
      </div>
    );
  }

  // Show embedded checkout
  if (showCheckout && clientSecret && stripePromise) {
    return (
      <div className="max-w-4xl mx-auto p-6">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold" style={{ color: '#2C3E50' }}>
              Subscribe to {selectedPlan?.key === 'pro' ? 'Pro' : 'Creator'}
            </h2>
            <p className="text-gray-600">
              {selectedPlan?.cycle === 'annual' ? 'Annual' : 'Monthly'} billing
            </p>
          </div>
          <Button 
            variant="outline" 
            onClick={() => {
              setShowCheckout(false);
              setClientSecret(null);
              setSelectedPlan(null);
            }}
          >
            Cancel
          </Button>
        </div>
        
        <div className="bg-white rounded-lg shadow-sm border p-6">
          <EmbeddedCheckoutProvider
            stripe={stripePromise}
            options={{ clientSecret }}
          >
            <EmbeddedCheckout />
          </EmbeddedCheckoutProvider>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold" style={{ color: '#2C3E50' }}>
            Billing & Subscription
          </h1>
          <p className="text-gray-600 mt-1">
            Manage your subscription and view usage
          </p>
        </div>
        {onBack && (
          <Button variant="outline" onClick={onBack}>
            ← Back to Dashboard
          </Button>
        )}
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800">{error}</p>
        </div>
      )}

      {/* Current Plan */}
      <Card>
        <CardHeader>
          <CardTitle>Current Plan</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-3">
                <h3 className="text-2xl font-bold capitalize">{currentTier}</h3>
                <Badge variant={isSubscribed ? 'default' : 'secondary'}>
                  {isSubscribed ? 'Active' : 'Free'}
                </Badge>
              </div>
              {subscription?.current_period_end && (
                <p className="text-sm text-gray-600 mt-1">
                  Renews on {formatDate(subscription.current_period_end)}
                </p>
              )}
            </div>
            {isSubscribed && (
              <Button onClick={openPortal} disabled={portalLoading}>
                {portalLoading ? 'Loading...' : 'Manage Subscription'}
              </Button>
            )}
          </div>

          {/* Usage Information */}
          {usage && (
            <div className="space-y-4 pt-4 border-t">
              {usage.max_episodes_month !== null && (
                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-gray-600">Episodes this month</span>
                    <span className="font-medium">
                      {usage.episodes_used_this_month} / {usage.max_episodes_month}
                    </span>
                  </div>
                  <Progress 
                    value={(usage.episodes_used_this_month / usage.max_episodes_month) * 100}
                    className="h-2"
                  />
                </div>
              )}
              
              {usage.max_processing_minutes_month !== null && (
                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-gray-600">Processing minutes this month</span>
                    <span className="font-medium">
                      {usage.processing_minutes_used_this_month} / {usage.max_processing_minutes_month}
                    </span>
                  </div>
                  <Progress 
                    value={(usage.processing_minutes_used_this_month / usage.max_processing_minutes_month) * 100}
                    className="h-2"
                  />
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Upgrade Options */}
      {!isSubscribed && (
        <>
          <div className="flex items-center justify-center gap-4">
            <span className="text-sm font-medium">Monthly</span>
            <button
              onClick={() => setAnnual(!annual)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                annual ? 'bg-blue-600' : 'bg-gray-200'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  annual ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
            <span className="text-sm font-medium">
              Annual <span className="text-green-600">(Save ~17%)</span>
            </span>
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            {tiers.map(tier => {
              const price = annual ? tier.annual : tier.monthly;
              const period = annual ? 'year' : 'month';
              const savings = annual ? Math.round(tier.monthly * 12 - tier.annual) : 0;

              return (
                <Card key={tier.key} className="relative hover:shadow-lg transition-shadow">
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between">
                      <span>{tier.name}</span>
                      {tier.key === 'creator' && (
                        <Badge>Most Popular</Badge>
                      )}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div>
                      <div className="flex items-baseline gap-1">
                        <span className="text-4xl font-bold">${price}</span>
                        <span className="text-gray-600">/{period}</span>
                      </div>
                      {annual && savings > 0 && (
                        <p className="text-sm text-green-600 mt-1">
                          Save ${savings}/year
                        </p>
                      )}
                    </div>

                    <ul className="space-y-2">
                      {tier.features.map((feature, idx) => (
                        <li key={idx} className="flex items-start gap-2">
                          <svg
                            className="w-5 h-5 text-green-500 mt-0.5 flex-shrink-0"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M5 13l4 4L19 7"
                            />
                          </svg>
                          <span className="text-sm">{feature}</span>
                        </li>
                      ))}
                    </ul>

                    <Button
                      className="w-full"
                      onClick={() => startEmbeddedCheckout(tier.key, annual ? 'annual' : 'monthly')}
                      style={{ backgroundColor: '#2C3E50' }}
                    >
                      Subscribe to {tier.name}
                    </Button>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
