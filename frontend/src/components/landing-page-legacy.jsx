/**
 * Legacy landing page preserved for archival purposes.
 * No longer imported in the application.
 */
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
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
import { useState, useEffect, useRef, useMemo } from "react"
import { makeApi, buildApiUrl, assetUrl } from "@/lib/apiClient.js";
import { useBrand } from "@/brand/BrandContext.jsx";
import Logo from "@/components/Logo.jsx";
import DOMPurify from "dompurify";
import { defaultLandingContent, normalizeLandingContent } from "@/lib/landingDefaults";
import LoginModal from "@/components/LoginModal.jsx";

const apiUrl = (path) => buildApiUrl(path);

const resolveAssetUrl = (path) => {
  if (!path || typeof path !== "string") return path;
  const trimmed = path.trim();
  if (!trimmed) return trimmed;
  if (/^[a-z][a-z0-9+.-]*:/i.test(trimmed) || trimmed.startsWith("//")) return trimmed;
  return assetUrl(trimmed);
};

export default function PodcastPlusLanding() {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);
  const [publicEpisodes, setPublicEpisodes] = useState([]);
  const [landingContent, setLandingContent] = useState(defaultLandingContent);
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

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(apiUrl("/api/public/landing"));
        if (!res.ok) {
          throw new Error("landing_fetch_failed");
        }
        const data = await res.json().catch(() => ({}));
        if (!cancelled) {
          setLandingContent(normalizeLandingContent(data));
        }
      } catch (_err) {
        if (!cancelled) {
          setLandingContent(defaultLandingContent);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const sanitizedHeroHtml = useMemo(
    () => DOMPurify.sanitize(landingContent.hero_html || defaultLandingContent.hero_html),
    [landingContent.hero_html]
  );

  const landingReviews = useMemo(
    () => (landingContent.reviews?.length ? landingContent.reviews : defaultLandingContent.reviews),
    [landingContent.reviews]
  );

  const landingFaqs = useMemo(
    () => (landingContent.faqs?.length ? landingContent.faqs : defaultLandingContent.faqs),
    [landingContent.faqs]
  );

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
          <div
            className="text-lg md:text-xl mb-12 text-gray-500 max-w-3xl mx-auto leading-relaxed text-center space-y-4"
            dangerouslySetInnerHTML={{ __html: sanitizedHeroHtml }}
          />

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
                {publicEpisodes.map((ep) => {
                  const playbackUrl = resolveAssetUrl(ep.proxy_playback_url || ep.final_audio_url || '');
                  return (
                    <Card key={ep.id} className="overflow-hidden">
                      <div className="h-40 bg-gray-100">
                        {ep.cover_url ? (
                          <img src={resolveAssetUrl(ep.cover_url)} alt={ep.title} className="w-full h-full object-cover" />
                        ) : (
                          <div className="h-full flex items-center justify-center text-gray-400">No Cover</div>
                        )}
                      </div>
                      <CardHeader>
                        <CardTitle className="text-lg line-clamp-1">{ep.title}</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <p className="text-sm text-gray-600 line-clamp-3 mb-2">{ep.description}</p>
                        {playbackUrl && <audio controls src={playbackUrl} className="w-full" />}
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            </div>
          )}
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold mb-6" style={{ color: "#2C3E50" }}>
              {landingContent.reviews_heading || defaultLandingContent.reviews_heading}
            </h2>
            { (landingContent.reviews_summary || defaultLandingContent.reviews_summary) && (
              <div className="flex justify-center items-center mb-8">
                <div className="flex">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Star key={i} className="w-6 h-6 fill-yellow-400 text-yellow-400" />
                  ))}
                </div>
                <span className="ml-2 text-lg text-gray-600">
                  {landingContent.reviews_summary || defaultLandingContent.reviews_summary}
                </span>
              </div>
            )}
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            {landingReviews.map((review, index) => {
              const stars = Math.max(0, Math.min(5, Math.round((review?.rating ?? 5))));
              const initials = (review?.author || "??")
                .split(/\s+/)
                .map((part) => part.charAt(0))
                .join("")
                .slice(0, 2)
                .toUpperCase();
              return (
                <Card key={`${review.author || "review"}-${index}`} className="border-0 shadow-lg hover:shadow-xl transition-all bg-white">
                  <CardContent className="p-8">
                    <div className="flex mb-4">
                      {Array.from({ length: 5 }).map((_, i) => (
                        <Star
                          key={i}
                          className={`w-4 h-4 ${i < stars ? "fill-yellow-400 text-yellow-400" : "text-gray-300"}`}
                        />
                      ))}
                    </div>
                    <p className="text-gray-700 leading-relaxed mb-6 text-lg">“{review.quote}”</p>
                    <div className="flex items-center">
                      <Avatar className="w-14 h-14 mr-4">
                        {review.avatar_url ? (
                          <AvatarImage src={review.avatar_url} alt={review.author || "Reviewer"} />
                        ) : null}
                        <AvatarFallback>{initials || "?"}</AvatarFallback>
                      </Avatar>
                      <div>
                        <h4 className="font-semibold text-lg" style={{ color: "#2C3E50" }}>
                          {review.author || "Happy Podcaster"}
                        </h4>
                        {review.role && <p className="text-gray-600">{review.role}</p>}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      </section>

      {/* FAQ Section */}
      <section id="faq" className="px-4 py-16 md:py-24" style={{ backgroundColor: "#ECF0F1" }}>
        <div className="container mx-auto max-w-4xl">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold mb-6" style={{ color: "#2C3E50" }}>
              {landingContent.faq_heading || defaultLandingContent.faq_heading}
            </h2>
            {(landingContent.faq_subheading || defaultLandingContent.faq_subheading) && (
              <p className="text-xl text-gray-600">
                {landingContent.faq_subheading || defaultLandingContent.faq_subheading}
              </p>
            )}
          </div>

          <div className="space-y-6">
            {landingFaqs.map((faq, index) => (
              <Card key={`${faq.question || "faq"}-${index}`} className="border-0 shadow-md bg-white">
                <CardContent className="p-6">
                  <h3 className="text-lg font-semibold mb-3" style={{ color: "#2C3E50" }}>
                    {faq.question}
                  </h3>
                  <p className="text-gray-600 leading-relaxed">{faq.answer}</p>
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
