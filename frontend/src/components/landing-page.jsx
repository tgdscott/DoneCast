import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Mic,
  Settings,
  Share2,
  Clock,
  Shield,
  Sparkles,
  CheckCircle,
  Star,
  Headphones,
  Play,
  ArrowRight,
  X,
} from "lucide-react"
import { useState, useEffect, useRef } from "react"
import { useAuth } from "@/AuthContext.jsx"
import { makeApi, buildApiUrl, resolveRuntimeApiBase } from "@/lib/apiClient";
import { useBrand } from "@/brand/BrandContext.jsx";
import Logo from "@/components/Logo.jsx";

const apiUrl = (path) => buildApiUrl(path);

const googleLoginUrl = (() => {
  const direct = buildApiUrl("/api/auth/login/google");
  if (/^https?:\/\//i.test(direct)) {
    return direct;
  }
  const base = resolveRuntimeApiBase();
  if (base) {
    return `${base.replace(/\/+$/, "")}/api/auth/login/google`;
  }
  // Rebrand: point to new API host (legacy host still accepted for a transition period)
  return "https://api.podcastplusplus.com/api/auth/login/google";
})();

const LoginModal = ({ onClose }) => {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [errorTone, setErrorTone] = useState("error");
  const [mode, setMode] = useState("login"); // 'login' | 'register' | 'verify'
  const [verifyCode, setVerifyCode] = useState("");
  const [verificationEmail, setVerificationEmail] = useState("");
  const [verifyExpiresAt, setVerifyExpiresAt] = useState(null); // timestamp ms
  const [resendPending, setResendPending] = useState(false);
  const [changeEmail, setChangeEmail] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const emailRef = useRef(null);
  const passwordRef = useRef(null);
  const fallbackTermsVersion = import.meta?.env?.VITE_TERMS_VERSION || "2025-09-19";
  // Terms acceptance moved to onboarding; no checkbox needed here
  const [acceptTerms, setAcceptTerms] = useState(true);
  const [termsInfo, setTermsInfo] = useState({ version: fallbackTermsVersion, url: "/terms" });
  const [termsLoading, setTermsLoading] = useState(false);
  const [registerSubmitting, setRegisterSubmitting] = useState(false);

  const normalizeMessage = (value, fallback) => {
    if (value == null || value === "") {
      return fallback;
    }
    if (typeof value === "string") {
      return value;
    }
    if (Array.isArray(value)) {
      const joined = value
        .map((item) => {
          if (!item) return "";
          if (typeof item === "string") return item;
          if (item?.msg) {
            const loc = Array.isArray(item.loc) ? item.loc.join(".") : item.loc;
            return loc ? `${item.msg} (${loc})` : item.msg;
          }
          try {
            return JSON.stringify(item);
          } catch (err) {
            return String(item);
          }
        })
        .filter(Boolean)
        .join(" ");
      return joined || fallback;
    }
    if (typeof value === "object") {
      if (value.detail && value.detail !== value) {
        return normalizeMessage(value.detail, fallback);
      }
      if (value.message && value.message !== value) {
        return normalizeMessage(value.message, fallback);
      }
      try {
        const serialized = JSON.stringify(value);
        if (serialized && serialized !== "{}") {
          return serialized;
        }
      } catch (err) {
        return fallback;
      }
    }
    return String(value) || fallback;
  };

  const showError = (message, tone = "error") => {
    setError(message);
    setErrorTone(tone);
  };

  const clearError = () => {
    setError("");
    setErrorTone("error");
  };

  useEffect(() => {
    let cancelled = false;
    const loadTerms = async () => {
      setTermsLoading(true);
      try {
        const res = await fetch(apiUrl("/api/auth/terms/info"));
        if (!res.ok) {
          throw new Error("terms_fetch_failed");
        }
        const data = await res.json().catch(() => ({}));
        if (!cancelled) {
          setTermsInfo({
            version: (data && data.version) || fallbackTermsVersion,
            url: (data && data.url) || "/terms",
          });
        }
      } catch (_err) {
        if (!cancelled) {
          setTermsInfo((prev) => ({
            version: (prev && prev.version) || fallbackTermsVersion,
            url: (prev && prev.url) || "/terms",
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
      const res = await fetch(apiUrl("/api/auth/token"), {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: params.toString(),
        credentials: "include",
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data && data.access_token) {
        login(data.access_token);
        onClose();
        return;
      }
      if (res.status === 401) {
        const detail = normalizeMessage(
          data?.detail || data?.message,
          "Invalid email or password."
        );
        if (/confirm your email/i.test(detail)) {
          showError(detail, "info");
        } else {
          showError(detail, "error");
        }
      } else {
        showError(
          normalizeMessage(
            data?.detail || data?.message,
            "An unexpected error occurred. Please try again."
          )
        );
      }
      throw new Error("login_failed");
    } catch (err) {
      if (err.message !== "login_failed") {
        showError("An unexpected error occurred. Please try again.");
      }
      throw err;
    }
  };

  const ensureFields = () => {
    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      showError("Email is required.");
      emailRef.current?.focus();
      return null;
    }
    if (!password) {
      showError("Password is required.");
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
    // No terms gating at signup — handled later in onboarding
    const trimmedEmail = ensureFields();
    if (!trimmedEmail) return;
    setEmail(trimmedEmail);
    const versionToSend = termsInfo?.version || fallbackTermsVersion;
    setRegisterSubmitting(true);
    let encounteredError = false;
    try {
      const res = await fetch(apiUrl("/api/auth/register"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: trimmedEmail,
          password,
          // Keep fields for backward compatibility; server ignores them now
          accept_terms: true,
          terms_version: versionToSend,
        }),
        credentials: "include",
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        encounteredError = true;
        if (res.status === 400) {
          showError(
            normalizeMessage(
              data?.detail || data?.message,
              "A user with this email already exists."
            )
          );
        } else if (res.status === 422) {
          showError("Invalid email or password format.");
        } else {
          showError(
            normalizeMessage(
              data?.detail || data?.message,
              "Registration error. Please try again."
            )
          );
        }
        return;
      }
      const data = await res.json().catch(() => null);
      const inactive = data && typeof data === 'object' && (data.is_active === false || data.isActive === false);
      if (inactive) {
        // Switch to verification mode
        setVerificationEmail(trimmedEmail);
        setVerifyExpiresAt(Date.now() + 15 * 60 * 1000);
        setMode('verify');
        setVerifyCode("");
        setChangeEmail(false);
        setNewEmail("");
        return;
      }
      await attemptEmailLogin(trimmedEmail, password); // auto-login if already active
      // No need to keep acceptance state here
    } catch (err) {
      if (!encounteredError) {
        showError("Registration error. Please try again.");
      }
    } finally {
      setRegisterSubmitting(false);
    }
  };

  // --- Derived UI state for submit button ---
  const submitDisabled =
    mode === "login"
      ? !email.trim() || !password
      : mode === 'register'
        ? registerSubmitting || !email.trim() || !password
        : false; // verify mode uses its own buttons

  const submitText =
    mode === "login" ? "Sign In" : registerSubmitting ? "Creating…" : "Create Account";

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <Card className="w-full max-w-md mx-4">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>{mode === "login" ? "Sign In" : "Create Account"}</CardTitle>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="w-4 h-4" />
          </Button>
        </CardHeader>
        <CardContent>
          {mode !== 'verify' && (
          <form onSubmit={mode === "login" ? handleEmailLogin : handleRegister} className="space-y-4">
            {error && (
              <div
                className={`rounded-md border px-3 py-2 text-sm ${
                  errorTone === "info"
                    ? "border-blue-200 bg-blue-50 text-blue-700"
                    : errorTone === "success"
                      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                      : "border-red-200 bg-red-50 text-red-700"
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
                  type={showPassword ? "text" : "password"}
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
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
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? "Hide" : "Show"}
                </Button>
              </div>
            </div>
            {/* Terms box removed: acceptance is handled later in onboarding */}
            <Button type="submit" className="w-full" disabled={submitDisabled}>
              {submitText}
            </Button>
            <button
              type="button"
              onClick={() => {
                setMode((m) => (m === "login" ? "register" : "login"));
                clearError();
                setRegisterSubmitting(false);
              }}
              className="w-full text-xs text-blue-600 hover:underline"
            >
              {mode === "login" ? "Need an account? Sign up" : "Have an account? Sign in"}
            </button>
          </form>
          )}
          {mode === 'verify' && (
            <div className="space-y-4" data-state="verify-flow">
              <div className="text-sm text-muted-foreground">We sent a 6‑digit code to <strong>{verificationEmail}</strong>. Enter it below or click the link in the email. This code expires in {verifyExpiresAt ? Math.max(0, Math.floor((verifyExpiresAt-Date.now())/60000)) : 15}m.</div>
              <div className="space-y-2">
                <Label htmlFor="verifyCode">Verification Code</Label>
                <Input
                  id="verifyCode"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  value={verifyCode}
                  autoFocus
                  onChange={(e)=> setVerifyCode(e.target.value.replace(/[^0-9]/g,''))}
                  placeholder="123456"
                  className="tracking-widest text-center text-lg"
                />
              </div>
              <div className="flex gap-2">
                <Button
                  disabled={verifyCode.length !== 6}
                  onClick={async ()=>{
                    clearError();
                    try {
                      const res = await fetch(apiUrl('/api/auth/confirm-email'), {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ email: verificationEmail, code: verifyCode }),
                        credentials: 'include'
                      });
                      const data = await res.json().catch(()=>({}));
                      if (!res.ok) {
                        showError(normalizeMessage(data?.detail || data?.message, 'Invalid or expired code.'));
                        return;
                      }
                      // Auto-login after successful activation
                      try { await attemptEmailLogin(verificationEmail, password); } catch {}
                    } catch (err) {
                      showError('Verification failed.');
                    }
                  }}
                >Confirm</Button>
                <Button variant="outline" onClick={async ()=>{
                  clearError();
                  if (resendPending) return;
                  setResendPending(true);
                  try {
                    await fetch(apiUrl('/api/auth/resend-verification'), { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ email: verificationEmail }) });
                    setVerifyExpiresAt(Date.now() + 15*60*1000);
                    showError('New code sent (check spam folder if not visible).','info');
                  } catch {}
                  setResendPending(false);
                }}>Resend</Button>
                <Button variant="ghost" onClick={()=>{ setMode('login'); clearError(); }}>Cancel</Button>
              </div>
              <div className="space-y-2">
                {!changeEmail && (
                  <button className="text-xs text-blue-600 hover:underline" type="button" onClick={()=>{ setChangeEmail(true); setNewEmail(verificationEmail); }}>Wrong email? Change it</button>
                )}
                {changeEmail && (
                  <div className="space-y-2 border rounded p-3">
                    <Label htmlFor="newEmail">New Email</Label>
                    <Input id="newEmail" type="email" value={newEmail} onChange={(e)=> setNewEmail(e.target.value)} />
                    <div className="flex gap-2">
                      <Button size="sm" disabled={!newEmail.trim() || newEmail===verificationEmail} onClick={async ()=>{
                        clearError();
                        try {
                          const res = await fetch(apiUrl('/api/auth/update-pending-email'), { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ old_email: verificationEmail, new_email: newEmail.trim() }) });
                          if (!res.ok) {
                            const d = await res.json().catch(()=>({}));
                            showError(normalizeMessage(d?.detail || d?.message, 'Unable to update email.'));
                            return;
                          }
                          setVerificationEmail(newEmail.trim());
                          setVerifyExpiresAt(Date.now() + 15*60*1000);
                          setVerifyCode('');
                          setChangeEmail(false);
                          showError('Email updated. New code sent.','info');
                        } catch { showError('Update failed'); }
                      }}>Save</Button>
                      <Button size="sm" variant="ghost" onClick={()=>{ setChangeEmail(false); }}>Cancel</Button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
          {mode !== 'verify' && (<div className="relative my-4">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-white px-2 text-muted-foreground">Or continue with</span>
            </div>
          </div>)}
          {mode !== 'verify' && (
            <a href={googleLoginUrl} className="block">
              <Button variant="outline" className="w-full">
                Sign In with Google
              </Button>
            </a>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default function PodcastPlusLanding() {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);
  const [publicEpisodes, setPublicEpisodes] = useState([]);
  const { brand } = useBrand();

  // Auto-open login if ?login=1 present
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      if (params.get("login") === "1") setIsLoginModalOpen(true);
    } catch (_) {}
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const data = await makeApi().get("/api/public/episodes");
        setPublicEpisodes(Array.isArray(data.items) ? data.items : []);
      } catch {}
    })();
  }, []);

  const handlePlayDemo = () => {
    setIsPlaying(!isPlaying);
  };

  return (
    <div className="min-h-screen bg-white">
      {isLoginModalOpen && <LoginModal onClose={() => setIsLoginModalOpen(false)} />}

      {/* Navigation Header */}
      <nav className="px-4 py-4 border-b border-gray-100">
        <div className="container mx-auto max-w-6xl flex justify-between items-center">
          <Logo size={28} lockup />
          <div className="hidden md:flex items-center space-x-8">
            <a href="#how-it-works" className="text-gray-600 hover:text-gray-800 transition-colors">
              How It Works
            </a>
            <a href="#testimonials" className="text-gray-600 hover:text-gray-800 transition-colors">
              Reviews
            </a>
            <a href="#faq" className="text-gray-600 hover:text-gray-800 transition-colors">
              FAQ
            </a>
            <a href="/subscriptions" className="text-gray-600 hover:text-gray-800 transition-colors">
              Subscriptions
            </a>
            <Button
              onClick={() => setIsLoginModalOpen(true)}
              variant="outline"
              className="border-2 bg-transparent"
              style={{ borderColor: "#2C3E50", color: "#2C3E50" }}
            >
              Sign In
            </Button>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="px-4 py-16 md:py-24 lg:py-32 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-blue-50 to-purple-50 opacity-30"></div>
        <div className="container mx-auto max-w-5xl text-center relative z-10">
          <Badge className="mb-6 px-4 py-2 text-sm font-medium" style={{ backgroundColor: "#ECF0F1", color: "#2C3E50" }}>
            🎉 Over 10,000 podcasters trust Podcast Plus Plus
          </Badge>

          <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold mb-6 leading-tight" style={{ color: "#2C3E50" }}>
            {brand.heroH1}
          </h1>
          <p className="text-xl md:text-2xl lg:text-3xl mb-8 text-gray-600 max-w-4xl mx-auto leading-relaxed">
            {brand.heroSub}
          </p>
          <p className="text-lg md:text-xl mb-12 text-gray-500 max-w-3xl mx-auto">
            Join thousands of creators who've discovered the joy of effortless podcasting.
            <strong className="text-gray-700"> Average setup time: Under 5 minutes.</strong>
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center mb-12">
            <Button
              size="lg"
              onClick={() => setIsLoginModalOpen(true)}
              className="text-lg px-8 py-6 font-semibold rounded-[var(--radius)] hover:opacity-90 transition-all transform hover:scale-105 shadow-lg"
            >
              Make my first episode
              <ArrowRight className="ml-2 w-5 h-5" />
            </Button>
            <Button
              variant="outline"
              size="lg"
              className="text-lg px-8 py-6 font-semibold rounded-[var(--radius)] border bg-secondary text-secondary-foreground hover:opacity-90 transition-all"
              onClick={handlePlayDemo}
            >
              <Play className="mr-2 w-5 h-5" />
              See how it works
            </Button>
          </div>

          <div className="flex flex-col sm:flex-row justify-center items-center gap-6 text-sm text-gray-500">
            <div className="flex items-center">
              <CheckCircle className="w-4 h-4 mr-2 text-green-500" />
              Free 14-day trial
            </div>
            <div className="flex items-center">
              <CheckCircle className="w-4 h-4 mr-2 text-green-500" />
              No credit card required
            </div>
            <div className="flex items-center">
              <CheckCircle className="w-4 h-4 mr-2 text-green-500" />
              Cancel anytime
            </div>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="px-4 py-12" style={{ backgroundColor: "#ECF0F1" }}>
        <div className="container mx-auto max-w-4xl">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
            <div>
              <div className="text-3xl md:text-4xl font-bold mb-2" style={{ color: "#2C3E50" }}>
                10K+
              </div>
              <div className="text-gray-600">Active Podcasters</div>
            </div>
            <div>
              <div className="text-3xl md:text-4xl font-bold mb-2" style={{ color: "#2C3E50" }}>
                50K+
              </div>
              <div className="text-gray-600">Episodes Published</div>
            </div>
            <div>
              <div className="text-3xl md:text-4xl font-bold mb-2" style={{ color: "#2C3E50" }}>
                95%
              </div>
              <div className="text-gray-600">Customer Satisfaction</div>
            </div>
            <div>
              <div className="text-3xl md:text-4xl font-bold mb-2" style={{ color: "#2C3E50" }}>
                5 Min
              </div>
              <div className="text-gray-600">Average Setup Time</div>
            </div>
          </div>
        </div>
      </section>

      {/* How It Works Section */}
      <section id="how-it-works" className="px-4 py-16 md:py-24">
        <div className="container mx-auto max-w-6xl">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold mb-6" style={{ color: "#2C3E50" }}>
              How It Works: Podcasting, Simplified.
            </h2>
            <p className="text-xl text-gray-600 max-w-3xl mx-auto">
              Three simple steps to go from idea to published podcast. No technical expertise required.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8 lg:gap-12">
            {/* Step 1 */}
            <div className="text-center group">
              <div className="relative">
                <div className="w-24 h-24 mx-auto mb-6 rounded-full bg-gradient-to-br from-blue-100 to-purple-100 flex items-center justify-center shadow-lg group-hover:shadow-xl transition-all transform group-hover:scale-105">
                  <Mic className="w-12 h-12" style={{ color: "#2C3E50" }} />
                </div>
                <Badge className="absolute -top-2 -right-2 bg-green-500 text-white text-xs px-2 py-1">Step 1</Badge>
              </div>
              <h3 className="text-xl md:text-2xl font-semibold mb-4" style={{ color: "#2C3E50" }}>
                Record or Generate Audio
              </h3>
              <p className="text-gray-600 text-lg leading-relaxed mb-4">
                Simply speak into your device, upload existing audio, or let our AI generate content from your notes.
              </p>
              <div className="text-sm text-gray-500">
                ✓ Works with any device • ✓ AI content generation • ✓ Multiple formats supported
              </div>
            </div>

            {/* Step 2 */}
            <div className="text-center group">
              <div className="relative">
                <div className="w-24 h-24 mx-auto mb-6 rounded-full bg-gradient-to-br from-green-100 to-blue-100 flex items-center justify-center shadow-lg group-hover:shadow-xl transition-all transform group-hover:scale-105">
                  <Settings className="w-12 h-12" style={{ color: "#2C3E50" }} />
                </div>
                <Badge className="absolute -top-2 -right-2 bg-green-500 text-white text-xs px-2 py-1">Step 2</Badge>
              </div>
              <h3 className="text-xl md:text-2xl font-semibold mb-4" style={{ color: "#2C3E50" }}>
                Automate Production & Polishing
              </h3>
              <p className="text-gray-600 text-lg leading-relaxed mb-4">
                Our AI handles editing, noise reduction, music, and professional formatting automatically.
              </p>
              <div className="text-sm text-gray-500">✓ Auto noise removal • ✓ Music & intros • ✓ Professional editing</div>
            </div>

            {/* Step 3 */}
            <div className="text-center group">
              <div className="relative">
                <div className="w-24 h-24 mx-auto mb-6 rounded-full bg-gradient-to-br from-purple-100 to-pink-100 flex items-center justify-center shadow-lg group-hover:shadow-xl transition-all transform group-hover:scale-105">
                  <Share2 className="w-12 h-12" style={{ color: "#2C3E50" }} />
                </div>
                <Badge className="absolute -top-2 -right-2 bg-green-500 text-white text-xs px-2 py-1">Step 3</Badge>
              </div>
              <h3 className="text-xl md:text-2xl font-semibold mb-4" style={{ color: "#2C3E50" }}>
                Publish & Share Instantly
              </h3>
              <p className="text-gray-600 text-lg leading-relaxed mb-4">
                Your podcast goes live on Spotify, Apple Podcasts, and 20+ platforms with just one click.
              </p>
              <div className="text-sm text-gray-500">✓ 20+ platforms • ✓ Automatic distribution • ✓ Analytics included</div>
            </div>
          </div>

          <div className="text-center mt-12">
            <Button
              size="lg"
              className="text-lg px-8 py-4 rounded-lg font-semibold text-white hover:opacity-90 transition-all"
              style={{ backgroundColor: "#2C3E50" }}
            >
              Try It Free for 14 Days
            </Button>
          </div>
        </div>
      </section>

      {/* Benefits Section */}
      <section className="px-4 py-16 md:py-24" style={{ backgroundColor: "#ECF0F1" }}>
        <div className="container mx-auto max-w-6xl">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold mb-8" style={{ color: "#2C3E50" }}>
              Why 10,000+ Creators Choose Podcast Plus Plus
            </h2>

            <div className="grid md:grid-cols-3 gap-8">
              <Card className="border-0 shadow-lg hover:shadow-xl transition-all transform hover:scale-105 bg-white">
                <CardContent className="p-8 text-center">
                  <Clock className="w-16 h-16 mx-auto mb-6" style={{ color: "#2C3E50" }} />
                  <h3 className="text-2xl font-semibold mb-4" style={{ color: "#2C3E50" }}>
                    Save 10+ Hours Per Episode
                  </h3>
                  <p className="text-gray-600 text-lg leading-relaxed">
                    What used to take days now takes minutes. Spend your time creating content, not fighting technology.
                  </p>
                </CardContent>
              </Card>

              <Card className="border-0 shadow-lg hover:shadow-xl transition-all transform hover:scale-105 bg-white">
                <CardContent className="p-8 text-center">
                  <Shield className="w-16 h-16 mx-auto mb-6" style={{ color: "#2C3E50" }} />
                  <h3 className="text-2xl font-semibold mb-4" style={{ color: "#2C3E50" }}>
                    Zero Technical Knowledge Required
                  </h3>
                  <p className="text-gray-600 text-lg leading-relaxed">
                    If you can send an email, you can create a professional podcast. We handle all the complex stuff.
                  </p>
                </CardContent>
              </Card>

              <Card className="border-0 shadow-lg hover:shadow-xl transition-all transform hover:scale-105 bg-white">
                <CardContent className="p-8 text-center">
                  <Sparkles className="w-16 h-16 mx-auto mb-6" style={{ color: "#2C3E50" }} />
                  <h3 className="text-2xl font-semibold mb-4" style={{ color: "#2C3E50" }}>
                    Studio-Quality Results
                  </h3>
                  <p className="text-gray-600 text-lg leading-relaxed">
                    Professional sound quality that rivals expensive studios, without the expensive equipment.
                  </p>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section id="testimonials" className="px-4 py-16 md:py-24">
        <div className="container mx-auto max-w-6xl">
          {publicEpisodes.length > 0 && (
            <div className="mb-16">
              <h2 className="text-3xl font-bold mb-6" style={{ color: "#2C3E50" }}>
                Recently Published with Plus Plus
              </h2>
              <div className="grid md:grid-cols-3 gap-6">
                {publicEpisodes.map((ep) => (
                  <Card key={ep.id} className="overflow-hidden">
                    <div className="h-40 bg-gray-100">
                      {ep.cover_url ? (
                        <img src={ep.cover_url} alt={ep.title} className="w-full h-full object-cover" />
                      ) : (
                        <div className="h-full flex items-center justify-center text-gray-400">No Cover</div>
                      )}
                    </div>
                    <CardHeader>
                      <CardTitle className="text-lg line-clamp-1">{ep.title}</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-sm text-gray-600 line-clamp-3 mb-2">{ep.description}</p>
                      {ep.final_audio_url && <audio controls src={ep.final_audio_url} className="w-full" />}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold mb-6" style={{ color: "#2C3E50" }}>
              Real Stories from Real Podcasters
            </h2>
            <div className="flex justify-center items-center mb-8">
              <div className="flex">
                {[...Array(5)].map((_, i) => (
                  <Star key={i} className="w-6 h-6 fill-yellow-400 text-yellow-400" />
                ))}
              </div>
              <span className="ml-2 text-lg text-gray-600">4.9/5 from 2,847 reviews</span>
            </div>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            <Card className="border-0 shadow-lg hover:shadow-xl transition-all bg-white">
              <CardContent className="p-8">
                <div className="flex mb-4">
                  {[...Array(5)].map((_, i) => (
                    <Star key={i} className="w-4 h-4 fill-yellow-400 text-yellow-400" />
                  ))}
                </div>
                <p className="text-gray-700 leading-relaxed mb-6 text-lg">
                  "I was terrified of the technical side of podcasting. Podcast Plus Plus made it so simple that I launched
                  my first episode in under 30 minutes! Now I have 50+ episodes and growing."
                </p>
                <div className="flex items-center">
                  <img
                    src="https://placehold.co/60x60/E2E8F0/A0AEC0?text=Avatar"
                    alt="Sarah Johnson"
                    width={60}
                    height={60}
                    className="rounded-full mr-4"
                  />
                  <div>
                    <h4 className="font-semibold text-lg" style={{ color: "#2C3E50" }}>
                      Sarah Johnson
                    </h4>
                    <p className="text-gray-600">Small Business Owner • 6 months on Plus Plus</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="border-0 shadow-lg hover:shadow-xl transition-all bg-white">
              <CardContent className="p-8">
                <div className="flex mb-4">
                  {[...Array(5)].map((_, i) => (
                    <Star key={i} className="w-4 h-4 fill-yellow-400 text-yellow-400" />
                  ))}
                </div>
                <p className="text-gray-700 leading-relaxed mb-6 text-lg">
                  "I've saved 15+ hours every week since switching to Podcast Plus Plus. The AI editing is incredible - it
                  sounds better than when I did it manually!"
                </p>
                <div className="flex items-center">
                  <img
                    src="https://placehold.co/60x60/E2E8F0/A0AEC0?text=Avatar"
                    alt="Robert Chen"
                    width={60}
                    height={60}
                    className="rounded-full mr-4"
                  />
                  <div>
                    <h4 className="font-semibold text-lg" style={{ color: "#2C3E50" }}>
                      Robert Chen
                    </h4>
                    <p className="text-gray-600">Retired Teacher • 1 year on Plus Plus</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="border-0 shadow-lg hover:shadow-xl transition-all bg-white">
              <CardContent className="p-8">
                <div className="flex mb-4">
                  {[...Array(5)].map((_, i) => (
                    <Star key={i} className="w-4 h-4 fill-yellow-400 text-yellow-400" />
                  ))}
                </div>
                <p className="text-gray-700 leading-relaxed mb-6 text-lg">
                  "My podcast now reaches 10,000+ listeners monthly. The automatic distribution to all platforms was a
                  game-changer for my reach!"
                </p>
                <div className="flex items-center">
                  <img
                    src="https://placehold.co/60x60/E2E8F0/A0AEC0?text=Avatar"
                    alt="Maria Rodriguez"
                    width={60}
                    height={60}
                    className="rounded-full mr-4"
                  />
                  <div>
                    <h4 className="font-semibold text-lg" style={{ color: "#2C3E50" }}>
                      Maria Rodriguez
                    </h4>
                    <p className="text-gray-600">Community Leader • 8 months on Plus Plus</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* FAQ Section */}
      <section id="faq" className="px-4 py-16 md:py-24" style={{ backgroundColor: "#ECF0F1" }}>
        <div className="container mx-auto max-w-4xl">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold mb-6" style={{ color: "#2C3E50" }}>
              Frequently Asked Questions
            </h2>
            <p className="text-xl text-gray-600">Everything you need to know about getting started with Podcast Plus Plus</p>
          </div>

          <div className="space-y-6">
            {[
              {
                q: "Do I need any technical experience to use Podcast Plus Plus?",
                a: "Absolutely not! Plus Plus is designed for complete beginners. If you can use email, you can create professional podcasts with our platform.",
              },
              {
                q: "How long does it take to publish my first episode?",
                a: "Most users publish their first episode within 30 minutes of signing up. Our average setup time is under 5 minutes, and episode creation takes just a few more minutes.",
              },
              {
                q: "What platforms will my podcast be available on?",
                a: "Your podcast will automatically be distributed to 20+ major platforms including Spotify, Apple Podcasts, Google Podcasts, and many more with just one click.",
              },
              {
                q: "Is there really a free trial with no credit card required?",
                a: "Yes! You get full access to all features for 14 days completely free. No credit card required, no hidden fees, and you can cancel anytime.",
              },
              {
                q: "What if I'm not satisfied with the service?",
                a: "We offer a 30-day money-back guarantee. If you're not completely satisfied, we'll refund your payment, no questions asked.",
              },
            ].map((faq, index) => (
              <Card key={index} className="border-0 shadow-md bg-white">
                <CardContent className="p-6">
                  <h3 className="text-lg font-semibold mb-3" style={{ color: "#2C3E50" }}>
                    {faq.q}
                  </h3>
                  <p className="text-gray-600 leading-relaxed">{faq.a}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA Section */}
      <section className="px-4 py-16 md:py-24">
        <div className="container mx-auto max-w-5xl text-center">
          <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold mb-6" style={{ color: "#2C3E50" }}>
            Ready to Start Your Podcast Journey?
          </h2>
          <p className="text-xl md:text-2xl mb-8 text-gray-600 leading-relaxed max-w-3xl mx-auto">
            Join over 10,000 creators who've discovered the joy of effortless podcasting. Start your free trial today -
            no credit card required.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center mb-8">
            <Button
              size="lg"
              onClick={() => setIsLoginModalOpen(true)}
              className="text-xl px-10 py-6 rounded-lg font-semibold text-white hover:opacity-90 transition-all transform hover:scale-105 shadow-lg"
              style={{ backgroundColor: "#2C3E50" }}
            >
              Start Your Free 14-Day Trial
              <ArrowRight className="ml-2 w-6 h-6" />
            </Button>
          </div>

          <div className="flex flex-col sm:flex-row justify-center items-center gap-6 text-sm text-gray-500 mb-8">
            <div className="flex items-center">
              <CheckCircle className="w-4 h-4 mr-2 text-green-500" />
              14-day free trial
            </div>
            <div className="flex items-center">
              <CheckCircle className="w-4 h-4 mr-2 text-green-500" />
              No credit card required
            </div>
            <div className="flex items-center">
              <CheckCircle className="w-4 h-4 mr-2 text-green-500" />
              30-day money-back guarantee
            </div>
          </div>

          <div className="text-center">
            <Badge className="px-4 py-2 text-sm font-medium" style={{ backgroundColor: "#ECF0F1", color: "#2C3E50" }}>
              🔒 Trusted by 10,000+ podcasters worldwide
            </Badge>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="px-4 py-12 border-t border-gray-200" style={{ backgroundColor: "#ECF0F1" }}>
        <div className="container mx-auto max-w-6xl">
          <div className="grid md:grid-cols-4 gap-8 mb-8">
            <div>
              <div className="flex items-center space-x-2 mb-4">
                <Headphones className="w-6 h-6" style={{ color: "#2C3E50" }} />
                <span className="text-xl font-bold" style={{ color: "#2C3E50" }}>
                  Podcast Plus Plus
                </span>
              </div>
              <p className="text-gray-600 mb-4">
                Making podcasting accessible to everyone, regardless of technical expertise.
              </p>
              <div className="flex space-x-4">
                <div className="w-8 h-8 bg-gray-300 rounded"></div>
                <div className="w-8 h-8 bg-gray-300 rounded"></div>
                <div className="w-8 h-8 bg-gray-300 rounded"></div>
              </div>
            </div>

            <div>
              <h4 className="font-semibold mb-4" style={{ color: "#2C3E50" }}>
                Product
              </h4>
              <ul className="space-y-2 text-gray-600">
                <li>
                  <a href="#" className="hover:text-gray-800 transition-colors">
                    Features
                  </a>
                </li>
                <li>
                  <a href="#" className="hover:text-gray-800 transition-colors">
                    Pricing
                  </a>
                </li>
                <li>
                  <a href="#" className="hover:text-gray-800 transition-colors">
                    Templates
                  </a>
                </li>
                <li>
                  <a href="#" className="hover:text-gray-800 transition-colors">
                    Integrations
                  </a>
                </li>
              </ul>
            </div>

            <div>
              <h4 className="font-semibold mb-4" style={{ color: "#2C3E50" }}>
                Support
              </h4>
              <ul className="space-y-2 text-gray-600">
                <li>
                  <a href="#" className="hover:text-gray-800 transition-colors">
                    Help Center
                  </a>
                </li>
                <li>
                  <a href="#" className="hover:text-gray-800 transition-colors">
                    Contact Us
                  </a>
                </li>
                <li>
                  <a href="#" className="hover:text-gray-800 transition-colors">
                    Tutorials
                  </a>
                </li>
                <li>
                  <a href="#" className="hover:text-gray-800 transition-colors">
                    Community
                  </a>
                </li>
              </ul>
            </div>

            <div>
              <h4 className="font-semibold mb-4" style={{ color: "#2C3E50" }}>
                Company
              </h4>
              <ul className="space-y-2 text-gray-600">
                <li>
                  <a href="#" className="hover:text-gray-800 transition-colors">
                    About Us
                  </a>
                </li>
                <li>
                  <a href="#" className="hover:text-gray-800 transition-colors">
                    Blog
                  </a>
                </li>
                <li>
                  <a href="#" className="hover:text-gray-800 transition-colors">
                    Careers
                  </a>
                </li>
                <li>
                  <a href="#" className="hover:text-gray-800 transition-colors">
                    Press
                  </a>
                </li>
              </ul>
            </div>
          </div>

          <div className="border-t border-gray-200 pt-8 flex flex-col md:flex-row justify-between items-center">
            <p className="text-gray-600 mb-4 md:mb-0">Podcast Plus Plus © 2025. All rights reserved.</p>
            <div className="flex space-x-6">
              <a href="/privacy" className="text-gray-600 hover:text-gray-800 transition-colors">
                Privacy Policy
              </a>
              <a href="/terms" className="hover:text-gray-800 transition-colors">
                Terms of Use
              </a>
              <a href="#" className="hover:text-gray-800 transition-colors">
                Cookie Policy
              </a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
