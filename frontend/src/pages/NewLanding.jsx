import React, { useEffect, useState } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import { useAuth } from '@/AuthContext.jsx';
import {
  ArrowRight,
  Globe,
  Headphones,
  Mic,
  Play,
  Radio,
  Shield,
  Sparkles,
  TrendingUp,
  Users,
  Zap,
  Star,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import './new-landing.css';
import LoginModal from '@/components/LoginModal.jsx';
import { makeApi } from '@/lib/apiClient';
import { defaultLandingContent, mergeLandingContent } from '@/lib/landingDefaults';

// Icon mapping helper (for features/pillars/differentiators that store tone but need icons)
const getIconForFeature = (title, tone) => {
  const iconMap = {
    'Unlimited Hosting': <Mic size={26} />,
    'AI-Powered Editing': <Sparkles size={26} />,
    'Global Distribution': <Globe size={26} />,
    'Lightning Fast': <Zap size={26} />,
    'Team Collaboration': <Users size={26} />,
    'Custom Player': <Headphones size={26} />,
  };
  return iconMap[title] || <Sparkles size={26} />;
};

const getIconForPillar = (title, tone) => {
  const iconMap = {
    'Faster': <Zap size={28} />,
    'Cheaper': <TrendingUp size={28} />,
    'Easier': <Sparkles size={28} />,
  };
  return iconMap[title] || <Sparkles size={28} />;
};

const getIconForDifferentiator = (title, tone) => {
  const iconMap = {
    'Patent-Pending Innovation': <Shield size={24} />,
    'Built For Everyone': <Users size={24} />,
    'Unbeatable Value': <TrendingUp size={24} />,
    'AI That Actually Works': <Sparkles size={24} />,
  };
  return iconMap[title] || <Sparkles size={24} />;
};

const footerLinks = [
  {
    title: 'Product',
    links: [
      { label: 'Features', href: '/features' },
      { label: 'FAQ', href: '/faq' },
    ],
  },
  {
    title: 'Company',
    links: [
      { label: 'About', href: '/about' },
      { label: 'Contact', href: '/contact' },
    ],
  },
  {
    title: 'Legal',
    links: [
      { label: 'Privacy', href: '/privacy' },
      { label: 'Terms', href: '/terms' },
    ],
  },
];

const Step = ({ number, color, title, description }) => (
  <div className="nl-step">
    <div
      className="nl-step-number"
      style={{
        borderColor: `hsl(var(--border))`,
        background: `hsl(var(--${color}) / 0.12)`,
        color: `hsl(var(--${color}))`,
      }}
    >
      {number}
    </div>
    <h3>{title}</h3>
    <p>{description}</p>
  </div>
);

const FeatureCard = ({ title, description, icon, tone }) => (
  <div className="nl-card">
    <div
      className="nl-card-icon"
      style={{
        background: `hsl(var(--${tone}) / 0.14)`,
        color: `hsl(var(--${tone}))`,
      }}
    >
      {icon}
    </div>
    <h3>{title}</h3>
    <p>{description}</p>
  </div>
);

const PillarCard = ({ title, description, icon, tone }) => (
  <div className="nl-card">
    <div
      className="nl-card-icon"
      style={{
        background: `hsl(var(--${tone}) / 0.16)`,
        color: `hsl(var(--${tone}))`,
      }}
    >
      {icon}
    </div>
    <h3>{title}</h3>
    <p>{description}</p>
  </div>
);

const Differentiator = ({ title, description, icon, tone }) => (
  <div className="flex items-start gap-4">
    <div
      className="nl-card-icon"
      style={{
        width: '48px',
        height: '48px',
        marginBottom: 0,
        background: `hsl(var(--${tone}) / 0.16)`,
        color: `hsl(var(--${tone}))`,
      }}
    >
      {icon}
    </div>
    <div>
      <h4 className="font-semibold text-lg mb-2">{title}</h4>
      <p className="nl-lead text-base">{description}</p>
    </div>
  </div>
);

const FooterColumn = ({ title, links }) => (
  <div>
    <p className="nl-footer-title">{title}</p>
    <ul className="nl-footer-links">
      {links.map((link) => (
        <li key={link.label}>
          {link.href.startsWith('/') ? (
            <Link to={link.href}>{link.label}</Link>
          ) : (
            <a href={link.href}>{link.label}</a>
          )}
        </li>
      ))}
    </ul>
  </div>
);

export default function NewLanding() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(() => searchParams.get('login') === '1');
  const [loginModalMode, setLoginModalMode] = useState('login'); // Track whether to show login or signup
  const navigate = useNavigate();
  const { isAuthenticated, hydrated } = useAuth();
  const [landingContent, setLandingContent] = useState(defaultLandingContent);
  const [expandedFaq, setExpandedFaq] = useState(null);

  // Fetch landing page content from API (all sections)
  useEffect(() => {
    let cancelled = false;
  const api = makeApi(null); // Public endpoint, no auth needed
  // API routes are mounted under /api on the backend. Use the full /api prefix
  // so buildApiUrl produces the correct production URL (e.g. https://api.podcastplusplus.com/api/public/landing).
  api.get('/api/public/landing')
      .then((data) => {
        if (!cancelled && data) {
          setLandingContent(mergeLandingContent(data));
        }
      })
      .catch((err) => {
        // Silently fall back to defaults - don't break the page
        console.warn('Failed to load landing content:', err);
      });
    return () => { cancelled = true; };
  }, []);

  // If a user is already authenticated (e.g., after OAuth redirect or returning visit),
  // move them into the application dashboard automatically instead of showing marketing.
  useEffect(() => {
    if (hydrated && isAuthenticated) {
      // Avoid redirect loop if already on dashboard route (shouldn't happen here though)
      navigate('/dashboard', { replace: true });
    }
  }, [hydrated, isAuthenticated, navigate]);

  useEffect(() => {
    const shouldOpen = searchParams.get('login') === '1';
    setIsLoginModalOpen(shouldOpen);
  }, [searchParams]);

  const openLoginModal = () => {
    setLoginModalMode('login');
    setIsLoginModalOpen(true);
    if (searchParams.get('login') === '1') {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.set('login', '1');
    setSearchParams(next, { replace: true });
  };

  const openSignupModal = () => {
    setLoginModalMode('register');
    setIsLoginModalOpen(true);
    if (searchParams.get('login') === '1') {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.set('login', '1');
    setSearchParams(next, { replace: true });
  };

  const closeLoginModal = () => {
    setIsLoginModalOpen(false);
    if (searchParams.get('login') !== '1') {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.delete('login');
    if (next.toString()) {
      setSearchParams(next, { replace: true });
    } else {
      setSearchParams({}, { replace: true });
    }
  };

  return (
    <div className="new-landing">
      {isLoginModalOpen && <LoginModal onClose={closeLoginModal} initialMode={loginModalMode} />}
      <nav className="nl-nav">
        <div className="nl-container">
          <div className="nl-nav-inner">
            <div className="nl-brand">
              <span className="nl-brand-icon">
                <Radio size={22} />
              </span>
              Podcast Plus Plus
            </div>
            <div className="nl-nav-links">
              <Link to="/features">Features</Link>
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

      <header className="nl-hero">
        <div className="nl-container nl-hero-grid">
          <div>
            <span className="nl-hero-label">
              <Sparkles size={16} /> {landingContent.hero.label}
            </span>
            <h1 className="nl-hero-title">
              {landingContent.hero.title} <span>{landingContent.hero.title_highlight}</span>
            </h1>
            <p className="nl-hero-description">
              {landingContent.hero.description}
            </p>
            <div className="nl-hero-actions">
              {isAuthenticated ? (
                <Link to="/onboarding" className="nl-button">
                  {landingContent.hero.cta_text}
                  <ArrowRight size={18} />
                </Link>
              ) : (
                <button type="button" className="nl-button" onClick={openSignupModal}>
                  {landingContent.hero.cta_text}
                  <ArrowRight size={18} />
                </button>
              )}

            </div>
            <div className="nl-hero-meta">
              {landingContent.hero.meta_items.map((text, idx) => (
                <div className="nl-hero-meta-item" key={idx}>
                  {idx === 0 ? <Sparkles size={18} /> : <Zap size={18} />}
                  {text}
                </div>
              ))}
            </div>
          </div>

          <div className="nl-hero-media">
            <figure className="nl-hero-frame">
              <img
                src="/modern-podcast-recording-studio-with-professional-.jpg"
                alt="Modern podcast recording studio"
                className="nl-hero-image"
                loading="eager"
              />
              <span className="nl-hero-overlay" aria-hidden="true" />
              <div
                className="nl-float-card"
                style={{ background: 'hsla(0, 0%, 100%, 0.92)' }}
              >
                <div
                  className="nl-float-icon"
                  style={{ background: 'hsl(var(--secondary) / 0.18)', color: 'hsl(var(--secondary))' }}
                >
                  <TrendingUp size={22} />
                </div>
                <div>
                  <p className="font-semibold text-base">Unlimited</p>
                  <p className="text-sm text-muted-foreground">Episodes &amp; Storage</p>
                </div>
              </div>
              <div
                className="nl-float-card nl-float-card-alt"
                style={{ background: 'hsla(0, 0%, 100%, 0.92)' }}
              >
                <div
                  className="nl-float-icon"
                  style={{ background: 'hsl(var(--accent) / 0.2)', color: 'hsl(var(--accent))' }}
                >
                  <Globe size={22} />
                </div>
                <div>
                  <p className="font-semibold text-base">Global</p>
                  <p className="text-sm text-muted-foreground">CDN Distribution</p>
                </div>
              </div>
            </figure>
          </div>
        </div>
      </header>

      <section className="nl-section nl-section-highlight">
        <div className="nl-container nl-split">
          <div className="nl-split-media">
            <figure className="nl-media-frame">
              <img
                src="/ai-podcast-editing-interface.jpg"
                alt="AI-powered editing interface"
                className="nl-media-image"
                loading="lazy"
              />
              <span className="nl-media-overlay" aria-hidden="true" />
            </figure>
            <div className="nl-media-card">
              <p className="font-semibold text-base">“This is the future of podcasting.”</p>
              <p className="text-sm text-muted-foreground">What our beta testers are saying</p>
            </div>
          </div>
          <div className="nl-split-content">
            <div className="nl-pill">{landingContent.ai_editing.pill_text}</div>
            <h2 className="nl-hero-title" style={{ fontSize: 'clamp(2.2rem, 4vw, 3.1rem)', marginBottom: '1.5rem' }}>
              {landingContent.ai_editing.title}
            </h2>
            <p className="nl-lead" style={{ marginBottom: '1.75rem' }}>
              {landingContent.ai_editing.description}
            </p>
            <ul className="nl-bullets">
              {landingContent.ai_editing.bullets.map((bullet, idx) => (
                <li key={idx}>{bullet}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="nl-section nl-section-muted" id="about">
        <div className="nl-container">
          <div className="nl-section-title">
            <h2>
              {landingContent.done_for_you.title} <span>{landingContent.done_for_you.title_highlight}</span>
            </h2>
            <p>
              {landingContent.done_for_you.description}
            </p>
          </div>
          <div className="nl-grid nl-grid-3">
            {landingContent.done_for_you.pillars.map((pillar) => (
              <PillarCard key={pillar.title} {...pillar} icon={getIconForPillar(pillar.title, pillar.tone)} />
            ))}
          </div>
          <div className="nl-media-highlight">
            <figure className="nl-media-frame">
              <img
                src="/podcast-creator-workflow.jpg"
                alt="Simple podcast creator workflow"
                className="nl-media-image"
                loading="lazy"
              />
              <span className="nl-media-overlay" aria-hidden="true" />
              <figcaption className="nl-media-caption">
                <h3>Your Voice. Your Vision. Your Control.</h3>
                <p>No middleman. No compromises. Just pure creative freedom.</p>
              </figcaption>
            </figure>
          </div>
        </div>
      </section>

      <section className="nl-section" id="pricing">
        <div className="nl-container">
          <div className="nl-section-title">
            <h2>
              {landingContent.three_steps.title} <span>{landingContent.three_steps.title_highlight}</span>
            </h2>
            <p>{landingContent.three_steps.description}</p>
          </div>
          <div className="nl-grid nl-grid-3 nl-steps">
            <span className="nl-step-connector" aria-hidden="true" />
            {landingContent.three_steps.steps.map((step) => (
              <Step key={step.number} {...step} />
            ))}
          </div>
          <div className="nl-cta">
            <Link to="/onboarding" className="nl-button">
              {landingContent.three_steps.cta_text}
              <ArrowRight size={18} />
            </Link>
          </div>
        </div>
      </section>

      <section className="nl-section" id="features">
        <div className="nl-container">
          <div className="nl-section-title">
            <h2>
              {landingContent.features.title} <span>{landingContent.features.title_highlight}</span>
            </h2>
            <p>{landingContent.features.description}</p>
          </div>
          <div className="nl-grid nl-grid-3">
            {landingContent.features.features.map((feature) => (
              <FeatureCard key={feature.title} {...feature} icon={getIconForFeature(feature.title, feature.tone)} />
            ))}
          </div>
        </div>
      </section>

      <section className="nl-section nl-section-alt">
        <div className="nl-container grid gap-10 lg:grid-cols-2 lg:items-center">
          <div>
            <h2 className="nl-hero-title" style={{ fontSize: 'clamp(2.2rem, 4vw, 3.2rem)', marginBottom: '1.5rem' }}>
              {landingContent.why.title} <span>{landingContent.why.title_highlight}</span>{landingContent.why.title_suffix}
            </h2>
            <p className="nl-lead" style={{ marginBottom: '2rem' }}>
              {landingContent.why.description}
            </p>
            <div className="grid gap-6">
              {landingContent.why.differentiators.map((item) => (
                <Differentiator key={item.title} {...item} icon={getIconForDifferentiator(item.title, item.tone)} />
              ))}
            </div>
          </div>
          <div className="nl-why-media">
            <figure className="nl-media-frame">
              <img
                src="/podcast-success-dashboard.jpg"
                alt="Podcast performance dashboard"
                className="nl-media-image"
                loading="lazy"
              />
              <span className="nl-media-overlay" aria-hidden="true" />
            </figure>
            <div className="nl-float-card nl-quote-card">
              <p className="font-semibold text-base">“This is the future of podcasting.”</p>
              <p className="text-sm text-muted-foreground">What our beta testers are saying</p>
            </div>
          </div>
        </div>
      </section>

      {/* Testimonials/Reviews Section (editable via admin) */}
      {landingContent.reviews && landingContent.reviews.length > 0 && (
        <section className="nl-section nl-section-muted">
          <div className="nl-container">
            <div className="nl-section-title">
              <h2>{landingContent.reviews_heading || 'What Our Users Say'}</h2>
              {landingContent.reviews_summary && (
                <p className="flex items-center justify-center gap-2 text-yellow-600 font-semibold">
                  <Star size={20} fill="currentColor" />
                  {landingContent.reviews_summary}
                </p>
              )}
            </div>
            <div className="nl-grid nl-grid-3">
              {landingContent.reviews.map((review, index) => (
                <div key={index} className="nl-card" style={{ padding: '2rem' }}>
                  <div className="flex items-center gap-3 mb-4">
                    {review.avatar_url ? (
                      <img 
                        src={review.avatar_url} 
                        alt={review.author} 
                        className="w-14 h-14 rounded-full object-cover"
                      />
                    ) : (
                      <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center text-primary font-semibold text-lg">
                        {review.author.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)}
                      </div>
                    )}
                    <div>
                      <p className="font-semibold text-base">{review.author}</p>
                      {review.role && <p className="text-sm text-muted-foreground">{review.role}</p>}
                    </div>
                  </div>
                  {review.rating && review.rating > 0 && (
                    <div className="flex gap-1 mb-3">
                      {[...Array(Math.floor(review.rating))].map((_, i) => (
                        <Star key={i} size={16} fill="currentColor" className="text-yellow-500" />
                      ))}
                    </div>
                  )}
                  <p className="text-base leading-relaxed text-foreground/90">{review.quote}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* FAQ Section (editable via admin) */}
      {landingContent.faqs && landingContent.faqs.length > 0 && (
        <section className="nl-section">
          <div className="nl-container" style={{ maxWidth: '800px' }}>
            <div className="nl-section-title">
              <h2>{landingContent.faq_heading || 'Frequently Asked Questions'}</h2>
              {landingContent.faq_subheading && (
                <p>{landingContent.faq_subheading}</p>
              )}
            </div>
            <div className="space-y-3">
              {landingContent.faqs.map((faq, index) => (
                <div 
                  key={index}
                  className="border border-border rounded-lg overflow-hidden bg-card"
                >
                  <button
                    type="button"
                    className="w-full px-6 py-4 flex items-center justify-between text-left hover:bg-muted/50 transition-colors"
                    onClick={() => setExpandedFaq(expandedFaq === index ? null : index)}
                  >
                    <span className="font-semibold text-base">{faq.question}</span>
                    {expandedFaq === index ? (
                      <ChevronUp size={20} className="text-muted-foreground flex-shrink-0" />
                    ) : (
                      <ChevronDown size={20} className="text-muted-foreground flex-shrink-0" />
                    )}
                  </button>
                  {expandedFaq === index && (
                    <div className="px-6 pb-4 pt-2 text-base leading-relaxed text-foreground/80 border-t border-border/50">
                      {faq.answer}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      <section className="nl-section nl-section-cta" style={{ position: 'relative', overflow: 'hidden' }}>
        <div className="nl-cta-pattern" aria-hidden="true" />
        <div className="nl-container" style={{ textAlign: 'center' }}>
          <div className="nl-pill" style={{ justifyContent: 'center', marginBottom: '1.5rem' }}>
            {landingContent.final_cta.pill_text}
          </div>
          <h2 className="nl-hero-title" style={{ fontSize: 'clamp(2.5rem, 4vw, 3.6rem)', marginBottom: '1.25rem' }}>
            {landingContent.final_cta.title}
          </h2>
          <p className="nl-lead" style={{ margin: '0 auto 2.25rem', maxWidth: '560px', color: 'hsl(var(--foreground) / 0.85)' }}>
            {landingContent.final_cta.description}
          </p>
          <div className="nl-hero-actions" style={{ justifyContent: 'center' }}>
            <Link to="/onboarding" className="nl-button" style={{ fontSize: '1.05rem', padding: '0.85rem 2.3rem' }}>
              {landingContent.final_cta.cta_text}
              <ArrowRight size={18} />
            </Link>

          </div>
          <p className="text-sm text-muted-foreground" style={{ marginTop: '1.75rem' }}>
            {landingContent.final_cta.fine_print}
          </p>
        </div>
      </section>

      <footer className="nl-footer">
        <div className="nl-container">
          <div className="nl-footer-grid">
            <div>
              <div className="nl-brand" style={{ marginBottom: '1rem' }}>
                <span className="nl-brand-icon">
                  <Radio size={20} />
                </span>
                Podcast Plus Plus
              </div>
              <p className="nl-lead" style={{ fontSize: '0.95rem' }}>
                Professional podcast hosting for the modern creator.
              </p>
            </div>
            {footerLinks.map((column) => (
              <FooterColumn key={column.title} {...column} />
            ))}
          </div>
          <div className="nl-footer-meta">&copy; {new Date().getFullYear()} Podcast Plus Plus. All rights reserved.</div>
        </div>
      </footer>
    </div>
  );
}
