import React, { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/apiClient";
import { Radio, ArrowRight } from "lucide-react";
import { useAuth } from "@/AuthContext.jsx";
import LoginModal from "@/components/LoginModal.jsx";
import "./new-landing.css";

// Fallback data in case API fails
const fallbackStandardTiers = [
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

export default function PublicPricing() {
  const { isAuthenticated } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(() => searchParams.get("login") === "1");
  const [loginModalMode, setLoginModalMode] = useState("login");
  const [pricingData, setPricingData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [annual, setAnnual] = useState(false);

  // Load pricing data from API - uses same endpoint as tier editor
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
          featureDefinitions: [],
        });
      } finally {
        setLoading(false);
      }
    };
    fetchPricingData();
  }, []);

  useEffect(() => {
    const shouldOpen = searchParams.get("login") === "1";
    setIsLoginModalOpen(shouldOpen);
  }, [searchParams]);

  const openLoginModal = () => {
    setLoginModalMode("login");
    setIsLoginModalOpen(true);
    if (searchParams.get("login") === "1") {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.set("login", "1");
    setSearchParams(next, { replace: true });
  };

  const openSignupModal = () => {
    setLoginModalMode("register");
    setIsLoginModalOpen(true);
    if (searchParams.get("login") === "1") {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.set("login", "1");
    setSearchParams(next, { replace: true });
  };

  const closeLoginModal = () => {
    setIsLoginModalOpen(false);
    if (searchParams.get("login") !== "1") {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.delete("login");
    if (next.toString()) {
      setSearchParams(next, { replace: true });
    } else {
      setSearchParams({}, { replace: true });
    }
  };

  const priceFor = (t) => {
    if (t.key === "enterprise") return "Contact Us";
    const amt = annual ? t.annual : t.monthly;
    if (!amt) return annual ? "—" : `$${t.monthly}/mo`;
    return `$${amt}/mo` + (annual ? " (billed annually)" : "");
  };

  const standardTiers = pricingData?.standardTiers || fallbackStandardTiers;
  const featureDefinitions = pricingData?.featureDefinitions || [];

  // Build rows from featureDefinitions (excluding monthly/annual since price is shown in header with toggle)
  const rows = useMemo(() => {
    if (featureDefinitions.length === 0) {
      // Filter out price row from fallback since it's shown in header
      return fallbackRows.filter(row => row.key !== "price");
    }
    // Convert featureDefinitions to rows format
    // Exclude monthly/annual price fields since we show computed price in header based on annual toggle
    const featureRows = featureDefinitions
      .filter(feature => {
        // Skip monthly/annual price fields since they're shown in header
        if (feature.fieldPath === "monthly" || feature.fieldPath === "annual") {
          return false;
        }
        // Skip if it's a price key (legacy)
        if (feature.key === "price") {
          return false;
        }
        return true;
      })
      .map((feature) => ({
        key: feature.key,
        label: feature.label,
        fieldPath: feature.fieldPath,
        type: feature.type,
        options: feature.options,
      }));
    return featureRows;
  }, [featureDefinitions]);

  const handleTrialClick = (tier, e) => {
    if (e) {
      e.preventDefault();
    }
    if (tier.contact) {
      navigate("/contact");
      return;
    }
    if (!isAuthenticated) {
      openSignupModal();
      return;
    }
    // If authenticated, navigate to onboarding
    navigate(`/onboarding?plan=${tier.key}`);
  };

  const renderPriceCell = (tier) => {
    return (
      <div className="flex flex-col items-center gap-3">
        <span className="text-2xl font-bold">{priceFor(tier)}</span>
        <div>
          {tier.contact ? (
            <Link to="/contact" className="text-blue-600 hover:underline">
              Contact Sales
            </Link>
          ) : (
            <button
              type="button"
              className={`nl-button inline-flex items-center gap-2 ${tier.popular ? "" : "nl-button-outline"}`}
              onClick={(e) => handleTrialClick(tier, e)}
            >
              Start Trial Now
              <ArrowRight size={16} />
            </button>
          )}
        </div>
      </div>
    );
  };

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
    <div className="new-landing min-h-screen bg-background">
      {isLoginModalOpen && <LoginModal onClose={closeLoginModal} initialMode={loginModalMode} />}
      
      {/* Navigation */}
      <nav className="nl-nav">
        <div className="nl-container">
          <div className="nl-nav-inner">
            <Link to="/" className="nl-brand">
              <span className="nl-brand-icon">
                <Radio size={22} />
              </span>
              DoneCast
            </Link>
            <div className="nl-nav-links">
              <Link to="/features">Features</Link>
              <Link to="/pricing-public">Pricing</Link>
              <Link to="/faq">FAQ</Link>
              <Link to="/about">About</Link>
            </div>
            <div className="nl-nav-cta">
              <button type="button" className="nl-button-outline" onClick={openLoginModal}>
                Log In
              </button>
              {isAuthenticated ? (
                <Link to="/onboarding" className="nl-button">
                  Start Free Trial
                </Link>
              ) : (
                <button type="button" className="nl-button" onClick={openSignupModal}>
                  Start Free Trial
                </button>
              )}
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="nl-section nl-section-highlight" style={{ paddingTop: "4rem", paddingBottom: "2rem" }}>
        <div className="nl-container">
          <div className="nl-section-title">
            <h1 className="nl-hero-title" style={{ fontSize: "clamp(2.5rem, 4vw, 3.6rem)", marginBottom: "1rem" }}>
              Choose the plan that fits your podcast
            </h1>
            <p className="nl-lead" style={{ maxWidth: "600px", margin: "0 auto" }}>
              All plans include powerful editing tools, publishing features, and friendly support. Upgrade anytime.
            </p>
          </div>
          
          {/* Annual/Monthly Toggle */}
          <div className="mt-6 flex justify-center">
            <div className="inline-flex items-center gap-3 rounded-full border border-border px-3 py-1 text-sm">
              <button
                type="button"
                onClick={() => setAnnual(false)}
                className={!annual ? "font-semibold text-foreground" : "text-muted-foreground hover:text-foreground"}
                aria-pressed={!annual}
              >
                Monthly
              </button>
              <span className="text-muted-foreground">|</span>
              <button
                type="button"
                onClick={() => setAnnual(true)}
                className={annual ? "font-semibold text-foreground" : "text-muted-foreground hover:text-foreground"}
                aria-pressed={annual}
              >
                Annual (Save 20%)
              </button>
            </div>
          </div>
          <p className="mt-2 text-center text-xs text-muted-foreground">Starter plan does not offer annual pricing.</p>
        </div>
      </section>

      {/* Pricing Table */}
      <section className="nl-section" style={{ paddingTop: "2rem" }}>
        <div className="nl-container" style={{ maxWidth: "1200px" }}>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  <th className="text-left p-4 align-bottom">&nbsp;</th>
                  {standardTiers.map((t) => (
                    <th key={t.key} className="p-4 text-center align-top">
                      <div
                        className={`rounded-lg border p-6 ${
                          t.popular ? "border-primary bg-primary/5" : "border-border bg-card"
                        }`}
                      >
                        <div className="flex flex-col items-center gap-2">
                          <h3 className="text-xl font-semibold">{t.name}</h3>
                          {t.popular && <Badge variant="secondary">{t.badge || "Most Popular"}</Badge>}
                        </div>
                        {renderPriceCell(t)}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.key} className="border-t border-border">
                    <td className="p-4 text-sm font-medium">{row.label}</td>
                    {standardTiers.map((t) => {
                      // Get value using fieldPath
                      const getValue = (obj, path) => {
                        if (!path) {
                          // Fallback to old behavior for backward compatibility
                          if (obj[row.key] !== undefined) return obj[row.key];
                          if (obj.features && obj.features[row.key] !== undefined) return obj.features[row.key];
                          return null;
                        }
                        const parts = path.split(".");
                        let value = obj;
                        for (const part of parts) {
                          if (value == null) return null;
                          value = value[part];
                        }
                        return value;
                      };

                      const value = getValue(t, row.fieldPath);

                      // Helper to normalize boolean values (handles both boolean and string "true"/"false")
                      const normalizeBoolean = (val) => {
                        if (val === true || val === "true" || val === "True" || val === "TRUE") return true;
                        if (val === false || val === "false" || val === "False" || val === "FALSE") return false;
                        return null;
                      };

                      // Render based on type
                      if (row.type === "boolean") {
                        const boolValue = normalizeBoolean(value);
                        return (
                          <td key={t.key} className="p-4 text-sm text-center">
                            <Check on={boolValue === true} />
                          </td>
                        );
                      }

                      if (row.type === "select") {
                        // For select type, show the string value if it's not a boolean
                        const boolValue = normalizeBoolean(value);
                        if (boolValue !== null) {
                          return (
                            <td key={t.key} className="p-4 text-sm text-center">
                              <Check on={boolValue === true} />
                            </td>
                          );
                        }
                        return (
                          <td key={t.key} className="p-4 text-sm text-center">
                            {typeof value === "string" ? value : <Check on={!!value} />}
                          </td>
                        );
                      }

                      // For text type, check if it's a boolean string and render accordingly
                      if (row.type === "text") {
                        const boolValue = normalizeBoolean(value);
                        if (boolValue !== null) {
                          return (
                            <td key={t.key} className="p-4 text-sm text-center">
                              <Check on={boolValue === true} />
                            </td>
                          );
                        }
                      }

                      // Default: text or number
                      return (
                        <td key={t.key} className="p-4 text-sm text-center">
                          {value != null ? String(value) : "—"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Notes */}
          <div className="mt-10 text-xs text-muted-foreground space-y-2 max-w-4xl mx-auto">
            <p>
              Credits: Monthly credits reset each billing period. Up to 10% of unused monthly credits roll over to the next period. Purchased credits never expire.
            </p>
            <p>
              *Executive plan allows manual override of max episode length on request. Contact support for details.
            </p>
            <p>
              All plans include a free trial. No credit card required to start.
            </p>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="nl-section nl-section-cta" style={{ position: "relative", overflow: "hidden" }}>
        <div className="nl-cta-pattern" aria-hidden="true" />
        <div className="nl-container" style={{ textAlign: "center" }}>
          <h2 className="nl-hero-title" style={{ fontSize: "clamp(2rem, 4vw, 2.8rem)", marginBottom: "1.25rem" }}>
            Ready to get started?
          </h2>
          <p className="nl-lead" style={{ margin: "0 auto 2rem", maxWidth: "560px" }}>
            Start your free trial today. No credit card required.
          </p>
          <div className="nl-hero-actions" style={{ justifyContent: "center" }}>
            {isAuthenticated ? (
              <Link to="/onboarding" className="nl-button" style={{ fontSize: "1.05rem", padding: "0.85rem 2.3rem" }}>
                Start Free Trial
                <ArrowRight size={18} />
              </Link>
            ) : (
              <button
                type="button"
                className="nl-button"
                style={{ fontSize: "1.05rem", padding: "0.85rem 2.3rem" }}
                onClick={openSignupModal}
              >
                Start Free Trial
                <ArrowRight size={18} />
              </button>
            )}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="nl-footer">
        <div className="nl-container">
          <div className="nl-footer-grid">
            <div>
              <div className="nl-brand" style={{ marginBottom: "1rem" }}>
                <span className="nl-brand-icon">
                  <Radio size={20} />
                </span>
                DoneCast
              </div>
              <p className="nl-lead" style={{ fontSize: "0.95rem" }}>
                Professional podcast hosting for the modern creator.
              </p>
            </div>
            <div>
              <p className="nl-footer-title">Product</p>
              <ul className="nl-footer-links">
                <li>
                  <Link to="/features">Features</Link>
                </li>
                <li>
                  <Link to="/pricing-public">Pricing</Link>
                </li>
                <li>
                  <Link to="/faq">FAQ</Link>
                </li>
              </ul>
            </div>
            <div>
              <p className="nl-footer-title">Company</p>
              <ul className="nl-footer-links">
                <li>
                  <Link to="/about">About</Link>
                </li>
                <li>
                  <Link to="/contact">Contact</Link>
                </li>
              </ul>
            </div>
            <div>
              <p className="nl-footer-title">Legal</p>
              <ul className="nl-footer-links">
                <li>
                  <Link to="/privacy">Privacy</Link>
                </li>
                <li>
                  <Link to="/terms">Terms</Link>
                </li>
              </ul>
            </div>
          </div>
          <div className="nl-footer-meta">&copy; {new Date().getFullYear()} DoneCast. All rights reserved.</div>
        </div>
      </footer>
    </div>
  );
}

