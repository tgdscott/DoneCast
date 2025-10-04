import React from 'react';
import { Link } from 'react-router-dom';
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
} from 'lucide-react';
import './new-landing.css';

const heroMeta = [
  { icon: <Sparkles size={18} />, text: 'Anyone can do this' },
  { icon: <Zap size={18} />, text: 'Setup in 5 minutes' },
];

const pillars = [
  {
    title: 'Faster',
    description: 'Record, edit, and publish in minutes. No back-and-forth with editors. No waiting days for revisions.',
    icon: <Zap size={28} />,
    tone: 'primary',
  },
  {
    title: 'Cheaper',
    description: 'One affordable subscription replaces expensive editors, hosting fees, and distribution services.',
    icon: <TrendingUp size={28} />,
    tone: 'secondary',
  },
  {
    title: 'Easier',
    description: 'So simple, your grandparents could use it. So powerful, professionals choose it. That\'s the magic.',
    icon: <Sparkles size={28} />,
    tone: 'accent',
  },
];

const features = [
  {
    title: 'Unlimited Hosting',
    description: 'Upload unlimited episodes with no storage limits. Your content, your way, without restrictions.',
    icon: <Mic size={26} />,
    tone: 'primary',
  },
  {
    title: 'AI-Powered Editing',
    description: 'Edit while you record with AI that removes mistakes, adds effects, and polishes your audio in real-time.',
    icon: <Sparkles size={26} />,
    tone: 'secondary',
  },
  {
    title: 'Global Distribution',
    description: 'Automatically distribute to Spotify, Apple Podcasts, Google Podcasts, and 20+ platforms.',
    icon: <Globe size={26} />,
    tone: 'accent',
  },
  {
    title: 'Lightning Fast',
    description: 'Global CDN ensures your episodes load instantly for listeners anywhere in the world.',
    icon: <Zap size={26} />,
    tone: 'primary',
  },
  {
    title: 'Team Collaboration',
    description: 'Invite team members, manage permissions, and collaborate seamlessly on your podcast.',
    icon: <Users size={26} />,
    tone: 'secondary',
  },
  {
    title: 'Custom Player',
    description: 'Beautiful, embeddable podcast player that matches your brand and engages listeners.',
    icon: <Headphones size={26} />,
    tone: 'accent',
  },
];

const differentiators = [
  {
    title: 'Patent-Pending Innovation',
    description: 'Technology you literally can\'t get anywhere else. We invented it.',
    icon: <Shield size={24} />,
    tone: 'primary',
  },
  {
    title: 'Built For Everyone',
    description: 'From first-timers to seasoned pros. From teens to retirees. Anyone can create here.',
    icon: <Users size={24} />,
    tone: 'secondary',
  },
  {
    title: 'Unbeatable Value',
    description: 'Replace your editor, hosting, and distribution services with one affordable platform.',
    icon: <TrendingUp size={24} />,
    tone: 'accent',
  },
  {
    title: 'AI That Actually Works',
    description: 'Not gimmicky features. Real AI that saves you hours and makes you sound professional.',
    icon: <Sparkles size={24} />,
    tone: 'primary',
  },
];

const footerLinks = [
  {
    title: 'Product',
    links: [
      { label: 'Features', href: '#features' },
      { label: 'Pricing', href: '/pricing' },
      { label: 'FAQ', href: '/in-development' },
    ],
  },
  {
    title: 'Company',
    links: [
      { label: 'About', href: '/in-development' },
      { label: 'Blog', href: '/in-development' },
      { label: 'Contact', href: '/in-development' },
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
  return (
    <div className="new-landing">
      <nav className="nl-nav">
        <div className="nl-container">
          <div className="nl-nav-inner">
            <div className="nl-brand">
              <span className="nl-brand-icon">
                <Radio size={22} />
              </span>
              PodcastPlusPlus
            </div>
            <div className="nl-nav-links">
              <a href="#features">Features</a>
              <a href="#pricing">Pricing</a>
              <a href="#about">About</a>
            </div>
            <div className="nl-nav-cta">
              <Link to="/app" className="nl-button-outline">
                Log In
              </Link>
              <Link to="/onboarding" className="nl-button">
                Start Free Trial
              </Link>
            </div>
          </div>
        </div>
      </nav>

      <header className="nl-hero">
        <div className="nl-container nl-hero-grid">
          <div>
            <span className="nl-hero-label">
              <Sparkles size={16} /> Patent-Pending AI Technology
            </span>
            <h1 className="nl-hero-title">
              Professional Podcasting <span>For Everyone</span>
            </h1>
            <p className="nl-hero-description">
              No experience needed. No technical skills required. No age limit. Just you and your voice. PodcastPlusPlus
              makes professional podcasting so easy, it\'s faster and cheaper than hiring someone else to do it.
            </p>
            <div className="nl-hero-actions">
              <Link to="/onboarding" className="nl-button">
                Start Your Free Trial
                <ArrowRight size={18} />
              </Link>
              <Link to="/in-development" className="nl-button-outline">
                <Play size={16} /> Watch Demo
              </Link>
            </div>
            <div className="nl-hero-meta">
              {heroMeta.map(({ icon, text }) => (
                <div className="nl-hero-meta-item" key={text}>
                  {icon}
                  {text}
                </div>
              ))}
            </div>
          </div>

          <div className="nl-hero-media">
            <div className="nl-hero-frame">
              <div className="nl-hero-placeholder">Immersive Studio Preview</div>
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
            </div>
          </div>
        </div>
      </header>

      <section className="nl-section nl-section-muted" id="about">
        <div className="nl-container">
          <div className="nl-section-title">
            <h2>
              Done For You, <span>By You</span>
            </h2>
            <p>
              Why pay someone else when you can do it yourself—faster, cheaper, and with complete creative control?
              PodcastPlusPlus is so intuitive that publishing your podcast takes less time and effort than explaining it to
              someone else.
            </p>
          </div>
          <div className="nl-grid nl-grid-3">
            {pillars.map((pillar) => (
              <PillarCard key={pillar.title} {...pillar} />
            ))}
          </div>
          <div className="nl-card" style={{ marginTop: '2.75rem' }}>
            <div className="grid gap-6 md:grid-cols-[1.25fr_1fr] md:items-end">
              <div>
                <h3 className="text-2xl font-semibold mb-2">Your Voice. Your Vision. Your Control.</h3>
                <p className="nl-lead">
                  No middleman. No compromises. Just pure creative freedom. We built the workflow so you can focus on what you
                  say—not how to edit it later.
                </p>
              </div>
              <div className="nl-pill justify-center md:justify-end">Launch in hours, not weeks</div>
            </div>
          </div>
        </div>
      </section>

      <section className="nl-section" id="pricing">
        <div className="nl-container">
          <div className="nl-section-title">
            <h2>
              From Idea to Published in <span>3 Simple Steps</span>
            </h2>
            <p>Seriously, it\'s this easy. No technical knowledge required. No learning curve. Just start talking.</p>
          </div>
          <div className="nl-grid nl-grid-3 nl-steps">
            <span className="nl-step-connector" aria-hidden="true" />
            <Step
              number="1"
              color="primary"
              title="Record"
              description="Hit record and start talking. Our AI handles the rest—removing mistakes, enhancing audio, and creating chapters."
            />
            <Step
              number="2"
              color="secondary"
              title="Review"
              description="Preview your episode with AI-applied edits. Make any final tweaks with our simple, intuitive editor."
            />
            <Step
              number="3"
              color="accent"
              title="Publish"
              description="One click distributes your podcast to Spotify, Apple Podcasts, and 20+ platforms. You're live!"
            />
          </div>
          <div className="nl-cta">
            <Link to="/onboarding" className="nl-button">
              Start Your First Episode Now
              <ArrowRight size={18} />
            </Link>
          </div>
        </div>
      </section>

      <section className="nl-section" id="features">
        <div className="nl-container">
          <div className="nl-section-title">
            <h2>
              Everything You Need to <span>Succeed</span>
            </h2>
            <p>Professional-grade tools that would normally cost thousands. All included in one simple platform.</p>
          </div>
          <div className="nl-grid nl-grid-3">
            {features.map((feature) => (
              <FeatureCard key={feature.title} {...feature} />
            ))}
          </div>
        </div>
      </section>

      <section className="nl-section nl-section-alt">
        <div className="nl-container grid gap-10 lg:grid-cols-2 lg:items-center">
          <div>
            <h2 className="nl-hero-title" style={{ fontSize: 'clamp(2.2rem, 4vw, 3.2rem)', marginBottom: '1.5rem' }}>
              Why <span>PodcastPlusPlus</span>?
            </h2>
            <p className="nl-lead" style={{ marginBottom: '2rem' }}>
              We've built something truly special here. Technology that doesn't exist anywhere else. A platform that makes the
              impossible feel effortless. This is podcasting, reimagined.
            </p>
            <div className="grid gap-6">
              {differentiators.map((item) => (
                <Differentiator key={item.title} {...item} />
              ))}
            </div>
          </div>
          <div className="nl-card">
            <h3 className="text-2xl font-semibold mb-3">“This is the future of podcasting.”</h3>
            <p className="nl-lead">
              What our beta testers are saying. Every workflow, every pixel, and every AI capability is designed to save you time
              while elevating your storytelling.
            </p>
              <div className="nl-pill" style={{ marginTop: '1.75rem', justifyContent: 'center' }}>
                Built with podcasters, for podcasters
              </div>
          </div>
        </div>
      </section>

      <section className="nl-section" style={{ position: 'relative', overflow: 'hidden' }}>
        <div className="nl-container" style={{ textAlign: 'center' }}>
          <div className="nl-pill" style={{ justifyContent: 'center', marginBottom: '1.5rem' }}>
            Ready when you are
          </div>
          <h2 className="nl-hero-title" style={{ fontSize: 'clamp(2.5rem, 4vw, 3.6rem)', marginBottom: '1.25rem' }}>
            Ready to Take Your Podcast to the Next Level?
          </h2>
          <p className="nl-lead" style={{ margin: '0 auto 2.25rem', maxWidth: '560px', color: 'hsl(var(--foreground) / 0.85)' }}>
            Join the next generation of podcasters who are building their audience with PodcastPlusPlus.
          </p>
          <div className="nl-hero-actions" style={{ justifyContent: 'center' }}>
            <Link to="/onboarding" className="nl-button" style={{ fontSize: '1.05rem', padding: '0.85rem 2.3rem' }}>
              Start Your Free Trial
              <ArrowRight size={18} />
            </Link>
            <Link
              to="/in-development"
              className="nl-button-outline"
              style={{ fontSize: '1.05rem', padding: '0.85rem 2.3rem', borderColor: 'hsl(var(--primary) / 0.6)' }}
            >
              Schedule a Demo
            </Link>
          </div>
          <p className="text-sm text-muted-foreground" style={{ marginTop: '1.75rem' }}>
            14-day free trial • No credit card required • Cancel anytime
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
                PodcastPlusPlus
              </div>
              <p className="nl-lead" style={{ fontSize: '0.95rem' }}>
                Professional podcast hosting for the modern creator.
              </p>
            </div>
            {footerLinks.map((column) => (
              <FooterColumn key={column.title} {...column} />
            ))}
          </div>
          <div className="nl-footer-meta">&copy; {new Date().getFullYear()} PodcastPlusPlus. All rights reserved.</div>
        </div>
      </footer>
    </div>
  );
}
