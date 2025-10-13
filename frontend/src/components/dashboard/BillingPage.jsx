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

export default function BillingPage({ token, onBack }) {
  const { refreshUser } = useAuth();
  const resolvedTimezone = useResolvedTimezone();
  const [subscription, setSubscription] = useState(null);
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [portalLoading, setPortalLoading] = useState(false);
  const [checkoutDetails, setCheckoutDetails] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [planPolling, setPlanPolling] = useState(false);
  const [annual, setAnnual] = useState(false);
  const { toast } = (() => { try { return useToast(); } catch { return { toast: () => {} }; } })();
  const tabIdRef = useRef(null);
  if(!tabIdRef.current) {
    try { tabIdRef.current = sessionStorage.getItem('ppp_tab_id') || Math.random().toString(36).slice(2); } catch { tabIdRef.current = Math.random().toString(36).slice(2); }
  }
  const bcRef = useRef(null);
  useEffect(()=>{ try { bcRef.current = new BroadcastChannel('ppp_checkout_owner'); bcRef.current.onmessage = (e)=>{
      if(e?.data?.type === 'owner_claimed' && e.data.owner !== tabIdRef.current) {
        // Another tab owns; if we have success params, attempt close quickly
        const params = new URLSearchParams(window.location.search);
        if(params.get('checkout')==='success') {
          window.close();
          setTimeout(()=>{ try { if(!document.hidden) window.location.replace('/'); } catch{} }, 200);
        }
      }
    }; } catch{} return ()=>{ try { bcRef.current && bcRef.current.close(); } catch{} } }, []);

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

  useEffect(()=>{ fetchAll(); }, [token]);

  // Handle coming back from Stripe checkout (can be popup or main tab)
  useEffect(()=>{
    const params = new URLSearchParams(window.location.search);
    const isSuccess = params.get('checkout') === 'success';
    const sessionId = params.get('session_id');
    const isPopup = typeof window !== 'undefined' && window.opener && window.name === 'ppp_stripe_checkout';
    if(!isSuccess) return; // nothing to do
    (async () => {
      // Ownership: only one tab should handle post-checkout. If another already did, try to close self.
      try {
        const owner = localStorage.getItem('ppp_checkout_owner');
        if(owner && owner !== tabIdRef.current) {
          // Secondary tab: auto-close/redirect
          window.close();
          setTimeout(()=>{ try { if(!document.hidden) window.location.replace('/'); } catch{} }, 150);
          return;
        } else if(!owner) {
          localStorage.setItem('ppp_checkout_owner', tabIdRef.current);
          try { bcRef.current?.postMessage({ type:'owner_claimed', owner: tabIdRef.current }); } catch{}
        }
      } catch {}
      try { toast({ title:'Processing Purchase', description:'Finalizing your subscription...', duration:4000 }); } catch {}
      // Try to capture checkout result (optional)
      if(sessionId) {
        for(let attempt=0; attempt<5; attempt++) {
          try {
            const api = makeApi(token);
            const data = await api.get(`/api/billing/checkout_result?session_id=${sessionId}`);
            setCheckoutDetails(data); setShowModal(true);
            try { const bc = new BroadcastChannel('ppp_billing'); bc.postMessage({ type:'checkout_success', payload:data }); bc.close(); } catch {}
            try { localStorage.setItem('ppp_last_checkout', JSON.stringify({ ts:Date.now(), data })); } catch {}
            break;
          } catch {}
          await new Promise(res=>setTimeout(res, 300*(attempt+1)));
        }
      }
      // Attempt immediate force sync (shortcut over webhook latency)
      let upgraded = false;
      if(sessionId) {
        for(let attempt=0; attempt<6 && !upgraded; attempt++) {
          try {
            const api = makeApi(token);
            const fsData = await api.post('/api/billing/force_sync_session', { session_id: sessionId });
            if(fsData?.plan_key && fsData.plan_key !== 'free') {
              setSubscription(s => ({ ...(s||{}), plan_key: fsData.plan_key, current_period_end: fsData.current_period_end }));
              upgraded = true;
              refreshUser({ force:true });
              setTimeout(()=>refreshUser({ force:true }), 1200); // double-tap to catch race
              toast({ title:'Subscription Upgraded', description:`You are now on the ${fsData.plan_key} plan.`, duration:5000 });
              try { const bc = new BroadcastChannel('ppp_billing'); bc.postMessage({ type:'subscription_updated', payload: fsData }); bc.close(); } catch {}
            }
          } catch {}
          if(!upgraded) await new Promise(res=>setTimeout(res, 800));
        }
      }
      if(!upgraded && !isPopup) {
        setPlanPolling(true);
        let tries=0;
        const poll=async()=>{
          tries+=1;
          try {
            const api = makeApi(token);
            const sub = await api.get('/api/billing/subscription');
            setSubscription(sub);
            if(sub.plan_key !== 'free') {
              refreshUser({ force:true });
              setTimeout(()=>refreshUser({ force:true }), 1200);
              toast({ title:'Subscription Upgraded', description:`You are now on the ${sub.plan_key} plan.`, duration:5000 });
              try { const bc = new BroadcastChannel('ppp_billing'); bc.postMessage({ type:'subscription_updated', payload: sub }); bc.close(); } catch {}
              setPlanPolling(false); return;
            }
          } catch {}
          if(tries < 15) setTimeout(poll, 1000); else { setPlanPolling(false); try { toast({ title:'Upgrade Pending', description:'Payment complete. Your plan will reflect the upgrade shortly.', duration:6000 }); } catch {} }
        };
        poll();
      }
      if(!isPopup) {
        fetchAll();
        try { window.history.replaceState(null,'', window.location.pathname); } catch {}
      }
      // Release ownership after short delay (so manual refresh doesn't spawn duplicates)
      setTimeout(()=>{ try { const owner = localStorage.getItem('ppp_checkout_owner'); if(owner === tabIdRef.current) localStorage.removeItem('ppp_checkout_owner'); } catch {} }, 5000);
      if(isPopup) {
        // Close popup after a brief delay once done.
        setTimeout(()=>{ try { window.close(); } catch{} }, 600);
      }
    })();
  }, [token, toast]);

  const startCheckout = async (planKey, billingCycle='monthly') => {
    try {
      setCheckoutLoading(true);
      const api = makeApi(token);
      const data = await api.post('/api/billing/checkout', { plan_key: planKey, billing_cycle: billingCycle });
      // Open popup for checkout
      const w = window.open(data.url, 'ppp_stripe_checkout', 'width=720,height=850,noopener');
      if(!w) {
        // Fallback: navigate current tab
        window.location.href = data.url;
      } else {
        try { w.focus(); } catch {}
      }
    } catch(e) {
      const msg = isApiError(e) ? (e.detail || e.error || e.message) : String(e);
      setError(msg);
    }
    finally { setCheckoutLoading(false); }
  };

  const openPortal = async () => {
    try {
      setPortalLoading(true);
      const api = makeApi(token);
      const data = await api.post('/api/billing/portal', {});
      window.location.href = data.url;
    } catch(e) {
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

  // Pricing data (Creator & Pro only for in-app billing)
  const tiers = useMemo(() => ([
    {
      key: 'starter', name: 'Starter', monthly: 19, annual: null,
      processing: '120 (2 hrs)', extraRate: '$6/hr', queue: '2 hrs, held 7 days',
      features: {
        uploadRecord: true, basicCleanup: true, manualPublish: true,
        flubber: false, intern: false, advancedIntern: false,
        sfxTemplates: false, analytics: false, multiUser: false, priorityQueue: false, premiumSupport: false,
      }
    },
    {
      key: 'creator', name: 'Creator', monthly: 39, annual: 31,
      processing: '600 (10 hrs)', extraRate: '$5/hr', queue: '10 hrs, held 14 days',
      features: {
        uploadRecord: true, basicCleanup: true, manualPublish: true,
        flubber: true, intern: true, advancedIntern: false,
        sfxTemplates: false, analytics: false, multiUser: false, priorityQueue: false, premiumSupport: false,
      },
      popular: true, badge: 'Most Popular',
    },
    {
      key: 'pro', name: 'Pro', monthly: 79, annual: 63,
      processing: '1500 (25 hrs)', extraRate: '$4/hr', queue: '25 hrs, held 30 days',
      features: {
        uploadRecord: true, basicCleanup: true, manualPublish: true,
        flubber: true, intern: true, advancedIntern: true,
        sfxTemplates: true, analytics: true, multiUser: false, priorityQueue: false, premiumSupport: false,
      },
    },
    {
      key: 'enterprise', name: 'Enterprise', monthly: null, annual: null,
      processing: '3600 (60 hrs)', extraRate: '$3/hr', queue: '60 hrs, held 60 days',
      features: {
        uploadRecord: true, basicCleanup: true, manualPublish: true,
        flubber: true, intern: true, advancedIntern: true,
        sfxTemplates: true, analytics: true, multiUser: true, priorityQueue: true, premiumSupport: true,
      },
      contact: true,
    },
  ]), []);

  const rows = useMemo(() => ([
    { key: 'price', label: 'Price' },
    { key: 'processing', label: 'Processing minutes / mo' },
    { key: 'extraRate', label: 'Extra minutes (rollover)' },
    { key: 'queue', label: 'Queue storage (unprocessed audio)' },
    { key: 'uploadRecord', label: 'Upload & record' },
    { key: 'basicCleanup', label: 'Basic cleanup (noise, trim)' },
    { key: 'manualPublish', label: 'Manual publish' },
    { key: 'flubber', label: 'Flubber (filler removal)' },
    { key: 'intern', label: 'Intern (spoken edits)' },
    { key: 'advancedIntern', label: 'Advanced Intern (multi-step edits)' },
    { key: 'sfxTemplates', label: 'Sound Effects & templates' },
    { key: 'analytics', label: 'Analytics' },
    { key: 'multiUser', label: 'Multi-user accounts' },
    { key: 'priorityQueue', label: 'Priority processing queue' },
    { key: 'premiumSupport', label: 'Premium support' },
  ]), []);

  const priceFor = (t) => {
    if (t.contact) return 'Contact Us';
    const amt = annual ? t.annual : t.monthly;
    if (amt == null) return annual ? '—' : `$${t.monthly}/mo`;
    return `$${amt}/mo` + (annual ? ' (billed annually)' : '');
  };

  function Check({ on }) {
    return <span aria-label={on ? 'Included' : 'Not included'} className={on ? 'text-green-600' : 'text-slate-400'}>{on ? '✅' : '–'}</span>;
  }

  const currentPlanKey = (subscription?.plan_key || 'free');
  const renewalIso = subscription?.current_period_end;
  const cancelAtEnd = !!(subscription?.cancel_at_period_end) || !!(subscription?.will_cancel_at);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          {onBack && <Button variant="ghost" onClick={onBack}>Back</Button>}
          <h2 className="text-2xl font-semibold">Subscriptions</h2>
        </div>
        <p className="text-sm text-muted-foreground sm:text-right">Toggle monthly or annual billing inside the plans table.</p>
      </div>
      {error && <div className="text-red-600 text-sm">{error}</div>}

      {/* Usage bar above table */}
      <Card>
        <CardContent className="pt-6">
          {!usage && <div className="text-sm text-gray-500">Loading usage...</div>}
          {usage && (() => {
            const usedMin = typeof usage.processing_minutes_used_this_month === 'number' ? usage.processing_minutes_used_this_month : (typeof usage.minutes_used === 'number' ? usage.minutes_used : null);
            const capMin = (typeof usage.max_processing_minutes_month === 'number') ? usage.max_processing_minutes_month : (usage.max_processing_minutes_month == null ? null : undefined);
            const leftMin = (capMin == null) ? '∞' : (usedMin == null ? null : Math.max(0, capMin - usedMin));
            const pct = (capMin && typeof usedMin === 'number') ? Math.min(100, (usedMin/Math.max(1,capMin))*100) : null;
            return (
              <div className="space-y-2 text-sm relative">
                <div className="flex justify-between"><span>Processing minutes</span><span>{usedMin ?? '—'} / {capMin == null ? '∞' : capMin}</span></div>
                {typeof pct === 'number' && <Progress value={pct} />}
                <div className="flex items-center justify-between">
                  {leftMin !== null && <div className="text-xs text-muted-foreground">Minutes left: {leftMin}</div>}
                  {currentPlanKey !== 'free' && renewalIso && (
                    <div className="text-[11px] text-muted-foreground">
                      {cancelAtEnd ? 'Your subscription ends on ' : 'Your subscription renews on '}
                      <span className="font-medium">{formatDate(renewalIso)}</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })()}
        </CardContent>
      </Card>

      {/* Pricing table */}
      <Card>
        <CardHeader className="flex flex-col gap-3 border-b border-slate-100 pb-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>Subscription Plans</CardTitle>
            <p className="text-sm text-muted-foreground">Compare plans and switch billing with the slider.</p>
          </div>
          <div className="flex flex-col items-end gap-1 sm:items-start">
            <div className="flex items-center gap-3">
              <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Billing</span>
              <div className="relative inline-flex h-9 w-44 items-center rounded-full bg-slate-200/80 p-1 shadow-inner">
                <span aria-hidden="true" className="pointer-events-none absolute inset-y-1 left-1 rounded-full bg-white shadow transition-transform duration-200 ease-in-out" style={{ width: 'calc(50% - 0.25rem)', transform: annual ? 'translateX(calc(100% + 0.5rem))' : 'translateX(0)' }} />
                <button type="button" onClick={()=>setAnnual(false)} aria-pressed={!annual} className={`relative z-10 flex-1 rounded-full px-2 text-center text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 ${!annual ? 'text-slate-900' : 'text-slate-500'}`}>Monthly</button>
                <button type="button" onClick={()=>setAnnual(true)} aria-pressed={annual} className={`relative z-10 flex-1 rounded-full px-2 text-center text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 ${annual ? 'text-slate-900' : 'text-slate-500'}`}>Annual</button>
              </div>
            </div>
            <span className="text-xs text-muted-foreground">Annual saves about 20%.</span>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse align-top min-w-[860px]">
              <thead>
                <tr>
                  <th className="text-left p-2 align-bottom text-sm">&nbsp;</th>
                  {tiers.map(t => (
                    <th key={t.key} className="p-2 text-left align-top min-w-[200px]">
                      <div className={`rounded-lg border p-3 ${t.popular ? 'border-blue-500' : 'border-slate-200'}`}>
                        <div className="flex items-center gap-2">
                          <h3 className="text-base font-semibold">{t.name}</h3>
                          {t.popular && <Badge variant="secondary">{t.badge || 'Most Popular'}</Badge>}
                          {currentPlanKey === t.key && <Badge variant="secondary" className="bg-green-100 text-green-700">Current Plan</Badge>}
                        </div>
                        <div className="mt-1 text-xl font-bold">{priceFor(t)}</div>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map(row => (
                  <tr key={row.key} className="border-t">
                    <td className="p-2 text-[13px] font-medium">{row.key === 'price' ? '' : row.label}</td>
                    {tiers.map(t => (
                      <td key={t.key} className="p-2 text-[13px] align-top">
                        {row.key === 'price' && (
                          <div className="flex items-center justify-center gap-3">
                            <div className="flex items-center gap-2">
                              {t.contact ? (
                                <Button asChild variant="secondary">
                                  <a href="/contact">Contact Sales</a>
                                </Button>
                              ) : currentPlanKey === t.key ? (
                                <Button disabled variant="secondary">Current</Button>
                              ) : (
                                <Button disabled={checkoutLoading} onClick={()=>startCheckout(t.key, annual? 'annual':'monthly')}>
                                  {annual ? `Choose ${t.name} (Annual)` : `Choose ${t.name}`}
                                </Button>
                              )}
                            </div>
                          </div>
                        )}
                        {row.key === 'processing' && t.processing}
                        {row.key === 'extraRate' && t.extraRate}
                        {row.key === 'queue' && t.queue}
                        {row.key !== 'price' && row.key !== 'processing' && row.key !== 'extraRate' && row.key !== 'queue' && (
                          <Check on={!!t.features[row.key]} />
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
                {/* Manage subscription row for non-free plans */}
                {currentPlanKey !== 'free' && (
                  <tr className="border-t">
                    <td className="p-2 text-[13px] font-medium">Manage</td>
                    {tiers.map(t => (
                      <td key={t.key} className="p-2 text-[13px]">
                        {currentPlanKey === t.key ? (
                          <Button disabled={portalLoading} onClick={openPortal}>Manage Subscription</Button>
                        ) : <span className="text-xs text-muted-foreground">—</span>}
                      </td>
                    ))}
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {planPolling && <div className="text-xs text-amber-600 mt-3">Finalizing upgrade...</div>}
        </CardContent>
      </Card>
      {showModal && <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
        <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6 space-y-4">
          <h3 className="text-xl font-semibold">Subscription Updated</h3>
          <div className="space-y-2 text-sm">
            <div>Plan: <span className="font-medium capitalize">{checkoutDetails?.plan_key}</span>{checkoutDetails?.billing_cycle && <span className="ml-1 text-gray-500">({checkoutDetails.billing_cycle})</span>}</div>
            {checkoutDetails?.plan_key !== 'free' && checkoutDetails?.renewal_date && <div>Renewal: {formatDate(checkoutDetails.renewal_date)}</div>}
            {checkoutDetails?.applied_credit && <div>Prorated credit from previous plan: ${checkoutDetails.applied_credit.toFixed(2)}</div>}
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={()=>setShowModal(false)}>Close</Button>
            <Button onClick={()=>{ setShowModal(false); if(onBack) onBack(); }}>Go to Dashboard</Button>
          </div>
        </div>
      </div>}
    </div>
  );
}
