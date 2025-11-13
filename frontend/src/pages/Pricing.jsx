import React, { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import Footer from "@/components/Footer.jsx";
import Logo from "@/components/Logo.jsx";
import { api } from "@/lib/apiClient";

// Fallback data in case API fails
const fallbackStandardTiers = [
  {
    key: "starter",
    name: "Starter",
    monthly: 19,
    annual: null, // no annual for Starter
    credits: "28,800",
    maxEpisodeLength: "40 min",
    queuePriority: "Low",
    queue: "2 hrs, held 7 days",
    features: {
      uploadRecord: true,
      basicCleanup: true,
      manualPublish: true,
      flubber: false,
      intern: false,
      advancedIntern: false,
      sfxTemplates: false,
      analytics: "Basic",
      multiUser: false,
      priorityQueue: false,
      premiumSupport: false,
    },
    cta: { label: "Get Started", href: "https://app.podcastpro.plus/signup?plan=starter" },
  },
  {
    key: "creator",
    name: "Creator",
    monthly: 39,
    annual: 31,
    credits: "72,000",
    maxEpisodeLength: "80 min",
    queuePriority: "Medium",
    queue: "10 hrs, held 14 days",
    features: {
      uploadRecord: true,
      basicCleanup: true,
      manualPublish: true,
      flubber: true,
      intern: true,
      advancedIntern: false,
      sfxTemplates: false,
      analytics: "Advanced",
      multiUser: false,
      priorityQueue: false,
      premiumSupport: false,
    },
    cta: { label: "Start Creating", href: "https://app.podcastpro.plus/signup?plan=creator" },
    popular: true,
    badge: "Most Popular",
  },
  {
    key: "pro",
    name: "Pro",
    monthly: 79,
    annual: 63,
    credits: "172,800",
    maxEpisodeLength: "120 min",
    queuePriority: "High",
    queue: "25 hrs, held 30 days",
    features: {
      uploadRecord: true,
      basicCleanup: true,
      manualPublish: true,
      flubber: true,
      intern: true,
      advancedIntern: true,
      sfxTemplates: true,
      analytics: "Full",
      multiUser: false,
      priorityQueue: false,
      premiumSupport: false,
    },
    cta: { label: "Go Pro", href: "https://app.podcastpro.plus/signup?plan=pro" },
  },
  {
    key: "executive",
    name: "Executive",
    monthly: 129,
    annual: 107,
    credits: "288,000",
    maxEpisodeLength: "240 min*",
    queuePriority: "Highest",
    queue: "50 hrs, held 60 days",
    features: {
      uploadRecord: true,
      basicCleanup: true,
      manualPublish: true,
      flubber: true,
      intern: true,
      advancedIntern: true,
      sfxTemplates: true,
      analytics: "Full",
      multiUser: "Coming soon",
      priorityQueue: true,
      premiumSupport: true,
    },
    cta: { label: "Go Executive", href: "https://app.podcastpro.plus/signup?plan=executive" },
  },
  {
    key: "enterprise",
    name: "Enterprise",
    monthly: null,
    annual: null,
    credits: "Custom",
    maxEpisodeLength: "Custom",
    queuePriority: "Highest",
    queue: "Custom",
    features: {
      uploadRecord: true,
      basicCleanup: true,
      manualPublish: true,
      flubber: true,
      intern: true,
      advancedIntern: true,
      sfxTemplates: true,
      analytics: "Full",
      multiUser: true,
      priorityQueue: true,
      premiumSupport: true,
    },
    cta: { label: "Contact Us" },
    contact: true,
  },
];

const fallbackEarlyAccessTiers = [
  {
    key: "starter",
    name: "Starter",
    monthly: 19,
    annual: null,
    credits: "28,800",
    maxEpisodeLength: "40 min",
    queuePriority: "Low",
    queue: "2 hrs, held 7 days",
    features: {
      uploadRecord: true,
      basicCleanup: true,
      manualPublish: true,
      flubber: false,
      intern: false,
      advancedIntern: false,
      sfxTemplates: false,
      analytics: "Basic",
      multiUser: false,
      priorityQueue: false,
      premiumSupport: false,
    },
    earlyOffers: [
      {
        title: "Standard Launch",
        price: "$19/mo",
        note: "Available Nov 1",
      },
    ],
    cta: { label: "Get Started", href: "https://app.podcastpro.plus/signup?plan=starter" },
  },
  {
    key: "creator",
    name: "Creator",
    monthly: 39,
    annual: 31,
    credits: "72,000",
    maxEpisodeLength: "80 min",
    queuePriority: "Medium",
    queue: "10 hrs, held 14 days",
    features: {
      uploadRecord: true,
      basicCleanup: true,
      manualPublish: true,
      flubber: true,
      intern: true,
      advancedIntern: false,
      sfxTemplates: false,
      analytics: "Advanced",
      multiUser: false,
      priorityQueue: false,
      premiumSupport: false,
    },
    earlyOffers: [
      {
        title: "Lifetime Deal",
        price: "$199 once",
        badge: "20 seats left",
      },
      {
        title: "Founders Annual",
        price: "$299/year",
        note: "Normally $468/yr • Ends Sept 30",
      },
      {
        title: "Partner Rate",
        price: "$10/mo (1st year)",
        note: "Invite-only • Converts to standard pricing",
      },
    ],
    cta: { label: "Start Creating", href: "https://app.podcastpro.plus/signup?plan=creator" },
    popular: true,
    badge: "Most Popular",
  },
  {
    key: "pro",
    name: "Pro",
    monthly: 79,
    annual: 63,
    credits: "172,800",
    maxEpisodeLength: "120 min",
    queuePriority: "High",
    queue: "25 hrs, held 30 days",
    features: {
      uploadRecord: true,
      basicCleanup: true,
      manualPublish: true,
      flubber: true,
      intern: true,
      advancedIntern: true,
      sfxTemplates: true,
      analytics: "Full",
      multiUser: false,
      priorityQueue: false,
      premiumSupport: false,
    },
    earlyOffers: [
      {
        title: "Lifetime Deal",
        price: "$399 once",
        badge: "20 seats left",
      },
      {
        title: "Founders Annual",
        price: "$599/year",
        note: "Normally $948/yr • Ends Sept 30",
      },
      {
        title: "Partner Rate",
        price: "$10/mo (1st year)",
        note: "Invite-only • Converts to standard pricing",
      },
    ],
    cta: { label: "Go Pro", href: "https://app.podcastpro.plus/signup?plan=pro" },
  },
  {
    key: "executive",
    name: "Executive",
    monthly: 129,
    annual: 107,
    credits: "288,000",
    maxEpisodeLength: "240 min*",
    queuePriority: "Highest",
    queue: "50 hrs, held 60 days",
    features: {
      uploadRecord: true,
      basicCleanup: true,
      manualPublish: true,
      flubber: true,
      intern: true,
      advancedIntern: true,
      sfxTemplates: true,
      analytics: "Full",
      multiUser: "Coming soon",
      priorityQueue: true,
      premiumSupport: true,
    },
    earlyOffers: [
      {
        title: "Standard Launch",
        price: "$129/mo",
        note: "Available Nov 1",
      },
    ],
    cta: { label: "Go Executive", href: "https://app.podcastpro.plus/signup?plan=executive" },
  },
  {
    key: "enterprise",
    name: "Enterprise",
    monthly: null,
    annual: null,
    credits: "Custom",
    maxEpisodeLength: "Custom",
    queuePriority: "Highest",
    queue: "Custom",
    features: {
      uploadRecord: true,
      basicCleanup: true,
      manualPublish: true,
      flubber: true,
      intern: true,
      advancedIntern: true,
      sfxTemplates: true,
      analytics: "Full",
      multiUser: true,
      priorityQueue: true,
      premiumSupport: true,
    },
    earlyOffers: [
      {
        title: "Custom Partnership",
        price: "Contact Sales",
        note: "Let’s tailor an early access plan for your network",
      },
    ],
    cta: { label: "Contact Us" },
    contact: true,
  },
];

// Fallback rows if featureDefinitions are not available
const fallbackRows = [
  { key: "price", label: "Price" },
  { key: "credits", label: "Monthly credits" },
  { key: "maxEpisodeLength", label: "Max episode length" },
  { key: "queuePriority", label: "Queue priority" },
  { key: "queue", label: "Queue storage (unprocessed audio)" },
  { key: "uploadRecord", label: "Upload & record" },
  { key: "basicCleanup", label: "Basic cleanup (noise, trim)" },
  { key: "manualPublish", label: "Manual publish" },
  { key: "flubber", label: "Flubber (filler removal)" },
  { key: "intern", label: "Intern (spoken edits)" },
  { key: "advancedIntern", label: "Advanced Intern (multi-step edits)" },
  { key: "sfxTemplates", label: "Sound Effects & templates" },
  { key: "analytics", label: "Analytics" },
  { key: "multiUser", label: "Multi-user accounts" },
  { key: "priorityQueue", label: "Priority processing queue" },
  { key: "premiumSupport", label: "Premium support" },
];

function Check({ on }) {
  return (
    <span aria-label={on ? "Included" : "Not included"} className={on ? "text-green-600" : "text-slate-400"}>
      {on ? "✅" : "–"}
    </span>
  );
}

export default function PricingPage() {
  const [mode, setMode] = useState("standard");
  const [annual, setAnnual] = useState(false);
  const [countdown, setCountdown] = useState(() => getCountdownParts());
  const [pricingData, setPricingData] = useState(null);
  const [loading, setLoading] = useState(true);

  // Load pricing data from API
  useEffect(() => {
    const fetchPricingData = async () => {
      try {
        setLoading(true);
        const data = await api.get("/api/admin/pricing/public");
        setPricingData(data);
      } catch (error) {
        console.error("Failed to load pricing data, using fallback:", error);
        // Use fallback data on error
        setPricingData({
          standardTiers: fallbackStandardTiers,
          earlyAccessTiers: fallbackEarlyAccessTiers,
        });
      } finally {
        setLoading(false);
      }
    };
    fetchPricingData();
  }, []);

  useEffect(() => {
    if (mode !== "early") return undefined;
    const interval = setInterval(() => setCountdown(getCountdownParts()), 1000);
    return () => clearInterval(interval);
  }, [mode]);

  const priceFor = (t) => {
    if (t.key === "enterprise") return "Contact Us";
    const amt = annual ? t.annual : t.monthly;
    if (!amt) return annual ? "—" : `$${t.monthly}/mo`;
    return `$${amt}/mo` + (annual ? " (billed annually)" : "");
  };

  const standardTiers = pricingData?.standardTiers || fallbackStandardTiers;
  const earlyAccessTiers = pricingData?.earlyAccessTiers || fallbackEarlyAccessTiers;
  const featureDefinitions = pricingData?.featureDefinitions || [];

  // Build rows from featureDefinitions, with price as special first row
  const rows = useMemo(() => {
    const priceRow = { key: "price", label: "Price" };
    if (featureDefinitions.length === 0) {
      return [priceRow, ...fallbackRows.slice(1)];
    }
    // Convert featureDefinitions to rows format
    const featureRows = featureDefinitions.map(feature => ({
      key: feature.key,
      label: feature.label,
      fieldPath: feature.fieldPath,
      type: feature.type,
      options: feature.options
    }));
    return [priceRow, ...featureRows];
  }, [featureDefinitions]);

  const visibleTiers = useMemo(
    () => (mode === "early" ? earlyAccessTiers : standardTiers),
    [mode, earlyAccessTiers, standardTiers]
  );

  const handleModeChange = (nextMode) => {
    setMode(nextMode);
    if (nextMode !== "standard") {
      setAnnual(false);
    }
  };

  const renderPriceCell = (tier) => {
    if (mode === "early") {
      return (
        <div className="space-y-3">
          {(tier.earlyOffers || []).map((offer, idx) => (
            <div
              key={`${tier.key}-offer-${idx}`}
              className="rounded-lg border border-blue-100 bg-blue-50/40 p-3 text-sm"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-blue-950">{offer.title}</span>
                {offer.badge && (
                  <Badge variant="secondary" className="bg-amber-100 text-amber-700">
                    {offer.badge}
                  </Badge>
                )}
              </div>
              <div className="mt-1 text-lg font-bold text-blue-900">{offer.price}</div>
              {offer.note && (
                <p className="mt-1 text-xs text-blue-700">{offer.note}</p>
              )}
            </div>
          ))}
          <div>
            {tier.contact ? (
              <a href="/contact" className="text-blue-600 hover:underline">
                Contact Sales
              </a>
            ) : (
              <Button
                asChild
                variant={tier.popular ? "default" : "secondary"}
              >
                <a href={tier.cta.href} className="no-underline">
                  {tier.cta.label}
                </a>
              </Button>
            )}
          </div>
        </div>
      );
    }

    return (
      <div className="flex items-center justify-between gap-3">
        <span className="text-lg font-semibold">{priceFor(tier)}</span>
        <div>
          {tier.contact ? (
            <a href="/contact" className="text-blue-600 hover:underline">
              Contact Sales
            </a>
          ) : (
            <Button
              asChild
              variant={tier.popular ? "default" : "secondary"}
            >
              <a href={tier.cta.href} className="no-underline">
                {tier.cta.label}
              </a>
            </Button>
          )}
        </div>
      </div>
    );
  };

  const countdownDisplay = countdown.ended
    ? "Offer ended"
    : `${countdown.days}d ${countdown.hours}h ${countdown.minutes}m ${countdown.seconds}s`;

  if (loading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading pricing information...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <header className="border-b">
        <div className="container mx-auto max-w-6xl flex items-center justify-between px-4 py-4">
          <Logo size={28} lockup />
          <a href="/" className="text-sm text-blue-600 hover:underline">Back to Home</a>
        </div>
      </header>

      {/* Hero */}
      <section className="container mx-auto max-w-4xl px-4 py-10 text-center">
        <h1 className="text-3xl md:text-4xl font-bold mb-3">
          {mode === "early" ? "Founders Early Access" : "Choose the plan that fits your podcast"}
        </h1>
        <p className="text-muted-foreground">
          {mode === "early"
            ? "Lock in founder-only rates before the public launch. These offers disappear after Sept 30."
            : "All plans include powerful editing tools, publishing features, and friendly support. Upgrade anytime."}
        </p>
        <div className="mt-6 inline-flex items-center gap-3 rounded-full border px-3 py-1 text-sm">
          <button
            type="button"
            onClick={() => handleModeChange("early")}
            className={
              mode === "early"
                ? "rounded-full bg-blue-600 px-3 py-1 font-semibold text-white"
                : "rounded-full px-3 py-1 text-slate-500 hover:text-slate-900"
            }
            aria-pressed={mode === "early"}
          >
            Founders Pricing
          </button>
          <span className="text-slate-300">|</span>
          <button
            type="button"
            onClick={() => handleModeChange("standard")}
            className={
              mode === "standard"
                ? "rounded-full bg-blue-600 px-3 py-1 font-semibold text-white"
                : "rounded-full px-3 py-1 text-slate-500 hover:text-slate-900"
            }
            aria-pressed={mode === "standard"}
          >
            Standard Pricing (Nov 1)
          </button>
        </div>
        {mode === "standard" && (
          <>
            <div className="mt-6 inline-flex items-center gap-3 rounded-full border px-3 py-1 text-sm">
              <button
                type="button"
                onClick={() => setAnnual(false)}
                className={!annual ? "font-semibold" : "text-slate-500"}
                aria-pressed={!annual}
              >
                Monthly
              </button>
              <span className="text-slate-300">|</span>
              <button
                type="button"
                onClick={() => setAnnual(true)}
                className={annual ? "font-semibold" : "text-slate-500"}
                aria-pressed={annual}
              >
                Annual (Save 20%)
              </button>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">Starter plan does not offer annual pricing.</p>
          </>
        )}
      </section>

      {mode === "early" && (
        <section className="container mx-auto max-w-5xl px-4 pb-6">
          <div className="relative overflow-hidden rounded-2xl border border-blue-200 bg-gradient-to-br from-blue-50 via-white to-blue-100 p-6 text-left shadow-sm">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div>
                <Badge variant="secondary" className="bg-blue-600/10 text-blue-800">
                  Limited Window
                </Badge>
                <h2 className="mt-3 text-2xl font-semibold text-blue-950">
                  Founders who join now keep their rates for life.
                </h2>
                <p className="mt-2 text-sm font-semibold uppercase tracking-wide text-blue-800">
                  Ends Sept 30
                </p>
              </div>
              <div className="rounded-xl border border-white/60 bg-white/80 px-4 py-3 text-center shadow">
                <p className="text-xs font-medium uppercase tracking-wide text-blue-600">Countdown to close</p>
                <p className="mt-1 font-mono text-lg text-blue-900">{countdownDisplay}</p>
              </div>
            </div>
          </div>
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border bg-white p-5 text-left shadow-sm">
              <h3 className="text-lg font-semibold text-slate-900">Lifetime Deal</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Pay once, own your plan forever. Limited to the first 20 creators across Creator and Pro tiers.
              </p>
              <div className="mt-4 space-y-2 text-sm">
                <p className="font-medium text-slate-900">Creator: <span className="font-semibold text-blue-700">$199</span> once</p>
                <p className="font-medium text-slate-900">Pro: <span className="font-semibold text-blue-700">$399</span> once</p>
              </div>
            </div>
            <div className="rounded-xl border bg-white p-5 text-left shadow-sm">
              <h3 className="text-lg font-semibold text-slate-900">Private Partner Deal</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                For partner groups you invite personally. Choose Creator or Pro for only $10/mo for the first year, then converts to normal pricing.
              </p>
              <p className="mt-4 text-sm font-medium text-amber-600">Not publicly available.</p>
            </div>
          </div>
        </section>
      )}

      {/* Pricing Table */}
      <section className="container mx-auto max-w-6xl px-4 pb-12">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className="text-left p-3 align-bottom">&nbsp;</th>
                {visibleTiers.map(t => (
                  <th key={t.key} className="p-3 text-left align-top">
                    <div className={`rounded-lg border p-4 ${t.popular ? "border-blue-500" : "border-slate-200"}`}>
                      <div className="flex items-center gap-2">
                        <h3 className="text-lg font-semibold">{t.name}</h3>
                        {t.popular && <Badge variant="secondary">{t.badge || "Most Popular"}</Badge>}
                      </div>
                      {mode === "early" ? (
                        <div className="mt-3 text-left text-sm">
                          <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">
                            Founder Offer
                          </p>
                          <p className="text-lg font-bold text-blue-900">
                            {t.earlyOffers?.[0]?.price || priceFor(t)}
                          </p>
                          {t.earlyOffers?.[0]?.title && (
                            <p className="text-xs text-blue-700">{t.earlyOffers[0].title}</p>
                          )}
                        </div>
                      ) : (
                        <div className="mt-1 text-2xl font-bold">{priceFor(t)}</div>
                      )}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={row.key} className="border-t">
                  <td className="p-3 text-sm font-medium">{row.label}</td>
                  {visibleTiers.map(t => {
                    // Handle price row specially
                    if (row.key === "price") {
                      return (
                        <td key={t.key} className="p-3 text-sm">
                          {renderPriceCell(t)}
                        </td>
                      );
                    }
                    
                    // Get value using fieldPath
                    const getValue = (obj, path) => {
                      if (!path) {
                        // Fallback to old behavior for backward compatibility
                        if (obj[row.key] !== undefined) return obj[row.key];
                        if (obj.features && obj.features[row.key] !== undefined) return obj.features[row.key];
                        return null;
                      }
                      const parts = path.split('.');
                      let value = obj;
                      for (const part of parts) {
                        if (value == null) return null;
                        value = value[part];
                      }
                      return value;
                    };
                    
                    const value = getValue(t, row.fieldPath);
                    
                    // Render based on type
                    if (row.type === "boolean") {
                      return (
                        <td key={t.key} className="p-3 text-sm">
                          <Check on={!!value} />
                        </td>
                      );
                    }
                    
                    if (row.type === "select") {
                      return (
                        <td key={t.key} className="p-3 text-sm">
                          {typeof value === "string" ? value : <Check on={!!value} />}
                        </td>
                      );
                    }
                    
                    // Default: text or number
                    return (
                      <td key={t.key} className="p-3 text-sm">
                        {value != null ? String(value) : "—"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* Notes / Future-proof */}
        <div className="mt-10 text-xs text-muted-foreground space-y-2">
          <p>
            Credits: Monthly credits reset each billing period. Up to 10% of unused monthly credits roll over to the next period. Purchased credits never expire.
          </p>
          <p>
            *Executive plan allows manual override of max episode length on request. Contact support for details.
          </p>
          <p>
            Early access deals vanish forever after Sept 30. Lifetime seats are capped at 20 and will show as sold out when they're gone.
          </p>
          <p>
            We're building more—this table is ready for future add-ons (social posting, clip generation, and more).
          </p>
        </div>
      </section>

      {/* Credits FAQ Section */}
      <section className="container mx-auto max-w-4xl px-4 py-12">
        <div className="rounded-xl border bg-white p-8 shadow-sm">
          <h2 className="text-2xl md:text-3xl font-bold mb-2">How Our Credit System Works</h2>
          <p className="text-muted-foreground mb-8">
            We like to keep things simple and transparent — you always know what you're getting and what it costs.
          </p>

          <div className="space-y-8">
            <div>
              <h3 className="text-xl font-semibold mb-3">Recording and Uploading</h3>
              <p className="text-muted-foreground mb-2">
                Every second of audio you record or upload uses <strong>1 credit</strong>.
              </p>
              <p className="text-muted-foreground">
                Want studio-quality sound? Our premium processing automatically upgrades lower-quality recordings (like from webcams or phones) for <strong>just 1 extra credit per second</strong>.
              </p>
            </div>

            <div>
              <h3 className="text-xl font-semibold mb-3">Editing and Finishing</h3>
              <p className="text-muted-foreground mb-2">
                When you're ready to assemble your final episode, that's where the magic happens.
              </p>
              <p className="text-muted-foreground">
                Final audio assembly costs <strong>3 credits per second</strong> — covering your intros, outros, and all the polishing that makes your episode shine.
              </p>
            </div>

            <div>
              <h3 className="text-xl font-semibold mb-3">Plan Overview</h3>
              <p className="text-muted-foreground mb-3">Choose the plan that fits your production style:</p>
              <ul className="list-disc list-inside space-y-2 text-muted-foreground ml-4">
                <li><strong>Starter:</strong> 28,800 credits = about 2 hours of finished audio</li>
                <li><strong>Creator:</strong> 72,000 credits = about 5 hours</li>
                <li><strong>Pro:</strong> 172,800 credits = about 12 hours</li>
                <li><strong>Executive:</strong> 288,000 credits = about 20 hours</li>
              </ul>
            </div>

            <div>
              <h3 className="text-xl font-semibold mb-3">Optional Features</h3>
              <p className="text-muted-foreground mb-3">Enhance your workflow with add-ons:</p>
              <ul className="list-disc list-inside space-y-2 text-muted-foreground ml-4">
                <li><strong>AI Titles, Descriptions & Tags:</strong> 1–3 credits each — perfect for quick content creation.</li>
                <li><strong>Intern Feature:</strong> 1 credit per answer — your built-in helper.</li>
                <li><strong>Text-to-Speech:</strong> 12–15 credits per second — natural, studio-grade voices for intros, outros, or responses.</li>
              </ul>
            </div>

            <div>
              <h3 className="text-xl font-semibold mb-3">Refunds and Flexibility</h3>
              <p className="text-muted-foreground mb-3">
                We're still in alpha, which means we're improving fast and keeping things fair.
              </p>
              <p className="text-muted-foreground mb-3">
                If something goes wrong, just request a refund in your subscription page — we'll make it right.
              </p>
              <p className="text-muted-foreground mb-2">You can also undo and get credits back:</p>
              <ul className="list-disc list-inside space-y-2 text-muted-foreground ml-4">
                <li>Delete within <strong>24 hours</strong> → refund of 2 out of every 3 credits.</li>
                <li>Delete within <strong>7 days</strong> → refund of 1 out of every 3 credits.</li>
                <li>After 7 days, refunds close automatically.</li>
              </ul>
            </div>

            <div className="pt-4 border-t">
              <p className="text-muted-foreground italic">
                Simple, fair, and transparent — so you can focus on creating, not calculating.
              </p>
            </div>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  );
}

function getCountdownParts() {
  const now = new Date();
  const currentYear = now.getFullYear();
  const target = new Date(currentYear, 8, 30, 23, 59, 59);
  const diff = target.getTime() - now.getTime();
  if (diff <= 0) {
    return { ended: true, days: 0, hours: 0, minutes: 0, seconds: 0 };
  }

  const totalSeconds = Math.floor(diff / 1000);
  const days = Math.floor(totalSeconds / (24 * 3600));
  const hours = Math.floor((totalSeconds % (24 * 3600)) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  return { ended: false, days, hours, minutes, seconds };
}
