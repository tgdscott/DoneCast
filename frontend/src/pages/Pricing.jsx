import React, { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import Footer from "@/components/Footer.jsx";
import Logo from "@/components/Logo.jsx";

const tiers = [
  {
    key: "starter",
    name: "Starter",
    monthly: 19,
    annual: null, // no annual for Starter
    processing: "120 (2 hrs)",
    extraRate: "$6/hr",
    queue: "2 hrs, held 7 days",
    features: {
      uploadRecord: true,
      basicCleanup: true,
      manualPublish: true,
      autopublishSpreaker: false,
      flubber: false,
      intern: false,
      advancedIntern: false,
      sfxTemplates: false,
      analytics: false,
      multiUser: false,
      priorityQueue: false,
      premiumSupport: false,
    },
    cta: { label: "Get Started" },
  },
  {
    key: "creator",
    name: "Creator",
    monthly: 39,
    annual: 31,
    processing: "600 (10 hrs)",
    extraRate: "$5/hr",
    queue: "10 hrs, held 14 days",
    features: {
      uploadRecord: true,
      basicCleanup: true,
      manualPublish: true,
      autopublishSpreaker: true,
      flubber: true,
      intern: true,
      advancedIntern: false,
      sfxTemplates: false,
      analytics: false,
      multiUser: false,
      priorityQueue: false,
      premiumSupport: false,
    },
    cta: { label: "Start Creating" },
    popular: true,
    badge: "Most Popular",
  },
  {
    key: "pro",
    name: "Pro",
    monthly: 79,
    annual: 63,
    processing: "1500 (25 hrs)",
    extraRate: "$4/hr",
    queue: "25 hrs, held 30 days",
    features: {
      uploadRecord: true,
      basicCleanup: true,
      manualPublish: true,
      autopublishSpreaker: true,
      flubber: true,
      intern: true,
      advancedIntern: true,
      sfxTemplates: true,
      analytics: true,
      multiUser: false,
      priorityQueue: false,
      premiumSupport: false,
    },
    cta: { label: "Go Pro" },
  },
  {
    key: "enterprise",
    name: "Enterprise",
    monthly: null,
    annual: null,
    processing: "3600 (60 hrs)",
    extraRate: "$3/hr",
    queue: "60 hrs, held 60 days",
    features: {
      uploadRecord: true,
      basicCleanup: true,
      manualPublish: true,
      autopublishSpreaker: true,
      flubber: true,
      intern: true,
      advancedIntern: true,
      sfxTemplates: true,
      analytics: true,
      multiUser: true,
      priorityQueue: true,
      premiumSupport: true,
    },
    cta: { label: "Contact Us" },
    contact: true,
  },
];

const rows = [
  { key: "price", label: "Price" },
  { key: "processing", label: "Processing minutes / mo" },
  { key: "extraRate", label: "Extra minutes (rollover)" },
  { key: "queue", label: "Queue storage (unprocessed audio)" },
  { key: "uploadRecord", label: "Upload & record" },
  { key: "basicCleanup", label: "Basic cleanup (noise, trim)" },
  { key: "manualPublish", label: "Manual publish" },
  { key: "autopublishSpreaker", label: "Auto-publish to Spreaker (+ linked platforms)" },
  { key: "flubber", label: "Flubber (filler removal)" },
  { key: "intern", label: "Intern (spoken edits)" },
  { key: "advancedIntern", label: "Advanced Intern (multi-step edits)" },
  { key: "sfxTemplates", label: "SFX & templates" },
  { key: "analytics", label: "Analytics (via Spreaker API)" },
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
  const [annual, setAnnual] = useState(false);
  const priceFor = (t) => {
    if (t.key === "enterprise") return "Contact Us";
    const amt = annual ? t.annual : t.monthly;
    if (!amt) return annual ? "—" : `$${t.monthly}/mo`;
    return `$${amt}/mo` + (annual ? " (billed annually)" : "");
  };
  const visibleTiers = useMemo(() => tiers, []);

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
        <h1 className="text-3xl md:text-4xl font-bold mb-3">Choose the plan that fits your podcast</h1>
        <p className="text-muted-foreground">All plans include powerful editing tools, publishing to Spreaker, and friendly support. Upgrade anytime.</p>
        {/* Toggle */}
        <div className="mt-6 inline-flex items-center gap-3 rounded-full border px-3 py-1 text-sm">
          <button onClick={() => setAnnual(false)} className={!annual ? "font-semibold" : "text-slate-500"}>Monthly</button>
          <span className="text-slate-300">|</span>
          <button onClick={() => setAnnual(true)} className={annual ? "font-semibold" : "text-slate-500"}>Annual (Save 20%)</button>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">Starter plan does not offer annual pricing.</p>
      </section>

      {/* Pricing Table */}
      <section className="container mx-auto max-w-6xl px-4 pb-12">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className="text-left p-3 align-bottom">&nbsp;</th>
                {visibleTiers.map(t => (
                  <th key={t.key} className="p-3 text-left">
                    <div className={`rounded-lg border p-4 ${t.popular ? "border-blue-500" : "border-slate-200"}`}>
                      <div className="flex items-center gap-2">
                        <h3 className="text-lg font-semibold">{t.name}</h3>
                        {t.popular && <Badge variant="secondary">{t.badge || "Most Popular"}</Badge>}
                      </div>
                      <div className="mt-1 text-2xl font-bold">{priceFor(t)}</div>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={row.key} className="border-t">
                  <td className="p-3 text-sm font-medium">{row.label}</td>
                  {visibleTiers.map(t => (
                    <td key={t.key} className="p-3 text-sm">
                      {row.key === "price" && (
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-lg font-semibold">{priceFor(t)}</span>
                          <div>
                            {t.contact ? (
                              <a href="/contact" className="text-blue-600 hover:underline">Contact Sales</a>
                            ) : (
                              <Button variant={t.popular ? "default" : "secondary"}>
                                {t.cta.label}
                              </Button>
                            )}
                          </div>
                        </div>
                      )}
                      {row.key === "processing" && t.processing}
                      {row.key === "extraRate" && t.extraRate}
                      {row.key === "queue" && t.queue}
                      {row.key !== "price" && row.key !== "processing" && row.key !== "extraRate" && row.key !== "queue" && (
                        <Check on={!!t.features[row.key]} />
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* Notes / Future-proof */}
        <div className="mt-10 text-xs text-muted-foreground space-y-2">
          <p>Minutes: monthly plans are “use it or lose it.” A la carte minutes roll over until used. Queue storage is plan-gated; no add-ons.</p>
          <p>We’re building more—this table is ready for future add-ons (social posting, clip generation, and more).</p>
        </div>
      </section>

      <Footer />
    </div>
  );
}
