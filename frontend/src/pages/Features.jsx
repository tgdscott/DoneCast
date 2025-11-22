import React from 'react';
import { Link } from 'react-router-dom';
import {
  Radio,
  Mic,
  Sparkles,
  Globe,
  Zap,
  Users,
  Headphones,
  FileAudio,
  Shield,
  TrendingUp,
  Edit3,
  Cloud,
  BarChart3,
  Settings,
  Sliders,
  Music,
  MessageSquare,
  Calendar,
  CheckCircle,
} from 'lucide-react';
import '../pages/new-landing.css';

const features = [
  {
    category: 'AI-Powered Production',
    icon: <Sparkles size={32} />,
    color: 'primary',
    items: [
      {
        title: 'Real-Time AI Editing',
        description: 'Our patent-pending AI processes your audio as you record. It identifies and removes filler words ("um", "uh", "like"), eliminates awkward pauses, and smooths transitions—all automatically.',
        icon: <Edit3 size={24} />,
      },
      {
        title: 'Spoken Editing Commands',
        description: 'Say "insert intro here" or "remove that section" while recording. Our AI understands natural language commands and executes them without you touching an editor.',
        icon: <MessageSquare size={24} />,
      },
      {
        title: 'Smart Audio Enhancement',
        description: 'Automatic noise reduction, volume normalization, and professional mastering. Your voice sounds crisp and clear regardless of recording environment.',
        icon: <Sliders size={24} />,
      },
      {
        title: 'AI Show Notes Generation',
        description: 'Automatically generate comprehensive show notes, key topics, timestamps, and SEO-optimized descriptions from your episode transcript.',
        icon: <FileAudio size={24} />,
      },
    ],
  },
  {
    category: 'Professional Editing Tools',
    icon: <Edit3 size={32} />,
    color: 'secondary',
    items: [
      {
        title: 'Visual Waveform Editor',
        description: 'Intuitive drag-and-drop editor with visual waveforms. Trim, cut, and arrange segments with precision. No audio engineering experience required.',
        icon: <Sliders size={24} />,
      },
      {
        title: 'Music & Sound Effects Library',
        description: 'Access thousands of royalty-free music tracks and sound effects. Add background music with automatic ducking when you speak.',
        icon: <Music size={24} />,
      },
      {
        title: 'Multi-Track Mixing',
        description: 'Record or import multiple audio tracks (host, guests, music) and mix them independently. Adjust levels, add effects, and create professional productions.',
        icon: <Settings size={24} />,
      },
      {
        title: 'Template System',
        description: 'Create reusable templates with your intro, outro, music, and structure. Apply them to new episodes in seconds for consistent branding.',
        icon: <CheckCircle size={24} />,
      },
    ],
  },
  {
    category: 'Unlimited Hosting & Distribution',
    icon: <Globe size={32} />,
    color: 'accent',
    items: [
      {
        title: 'Unlimited Storage',
        description: 'No limits on episode count, file sizes, or total storage. Upload as many episodes as you want, as long as you want. Your content, your way.',
        icon: <Cloud size={24} />,
      },
      {
        title: 'Global CDN Delivery',
        description: 'Lightning-fast content delivery via Google Cloud\'s global network. Your episodes load instantly for listeners anywhere in the world.',
        icon: <Zap size={24} />,
      },
      {
        title: 'One-Click Distribution',
        description: 'Automatically publish to Spotify, Apple Podcasts, Google Podcasts, Amazon Music, Stitcher, TuneIn, iHeartRadio, and 20+ other platforms with one click.',
        icon: <Globe size={24} />,
      },
      {
        title: 'RSS Feed Management',
        description: 'Professional RSS feed automatically generated and updated. Full control over metadata, categories, explicit content warnings, and podcast artwork.',
        icon: <FileAudio size={24} />,
      },
    ],
  },
  {
    category: 'Analytics & Growth',
    icon: <BarChart3 size={32} />,
    color: 'primary',
    items: [
      {
        title: 'Comprehensive Analytics',
        description: 'Track downloads, unique listeners, listening duration, and engagement metrics. See which episodes resonate and understand your audience growth.',
        icon: <TrendingUp size={24} />,
      },
      {
        title: 'Geographic Insights',
        description: 'Discover where your listeners are located. Optimize publishing times and content for your core audience demographics.',
        icon: <Globe size={24} />,
      },
      {
        title: 'Platform Performance',
        description: 'See which podcast platforms drive the most engagement. Optimize your promotional strategy based on real data.',
        icon: <BarChart3 size={24} />,
      },
      {
        title: 'IAB-Certified Stats',
        description: 'Industry-standard download metrics certified by the Interactive Advertising Bureau. Accurate data advertisers trust.',
        icon: <Shield size={24} />,
      },
    ],
  },
  {
    category: 'Team Collaboration',
    icon: <Users size={32} />,
    color: 'secondary',
    items: [
      {
        title: 'Multi-User Access',
        description: 'Invite team members, co-hosts, producers, or editors. Each gets their own login with role-based permissions.',
        icon: <Users size={24} />,
      },
      {
        title: 'Role-Based Permissions',
        description: 'Control who can edit, publish, or manage settings. Keep your content secure while enabling collaboration.',
        icon: <Shield size={24} />,
      },
      {
        title: 'Review & Approval Workflow',
        description: 'Set up approval workflows where editors prepare episodes and hosts review before publishing. Perfect for professional teams.',
        icon: <CheckCircle size={24} />,
      },
      {
        title: 'Activity History',
        description: 'Track all changes with detailed activity logs. See who edited what and when. Restore previous versions if needed.',
        icon: <Calendar size={24} />,
      },
    ],
  },
  {
    category: 'Advanced Features',
    icon: <Settings size={32} />,
    color: 'accent',
    items: [
      {
        title: 'Scheduled Publishing',
        description: 'Plan your content calendar weeks in advance. Episodes automatically publish at your chosen date and time.',
        icon: <Calendar size={24} />,
      },
      {
        title: 'Custom Podcast Player',
        description: 'Beautiful, embeddable player for your website. Customizable colors, branding, and sharing features. Works everywhere.',
        icon: <Headphones size={24} />,
      },
      {
        title: 'Private Podcasts',
        description: 'Create password-protected or subscriber-only podcasts. Perfect for premium content, courses, or internal communications.',
        icon: <Shield size={24} />,
      },
      {
        title: 'Import Existing Podcast',
        description: 'Migrate from any platform seamlessly. We import all your episodes, artwork, and RSS history. Keep your stats and subscribers.',
        icon: <Cloud size={24} />,
      },
      {
        title: 'Multiple Podcasts',
        description: 'Manage multiple shows from one account. Different topics, formats, or audiences—all in one dashboard.',
        icon: <Mic size={24} />,
      },
      {
        title: 'API Access',
        description: 'Full REST API for developers. Automate workflows, integrate with other tools, or build custom applications.',
        icon: <Settings size={24} />,
      },
    ],
  },
];

function FeatureCard({ title, description, icon }) {
  return (
    <div className="feature-detail-card">
      <div className="feature-icon-wrapper">{icon}</div>
      <div>
        <h3 className="feature-card-title">{title}</h3>
        <p className="feature-card-description">{description}</p>
      </div>
    </div>
  );
}

function FeatureCategory({ category, icon, color, items }) {
  return (
    <section className="feature-category-section">
      <div className="feature-category-header">
        <div
          className="feature-category-icon"
          style={{
            background: `hsl(var(--${color}) / 0.15)`,
            color: `hsl(var(--${color}))`,
          }}
        >
          {icon}
        </div>
        <h2 className="feature-category-title">{category}</h2>
      </div>
      <div className="feature-grid">
        {items.map((item, idx) => (
          <FeatureCard key={idx} {...item} />
        ))}
      </div>
    </section>
  );
}

export default function Features() {
  return (
    <div className="new-landing">
      <nav className="nl-nav">
        <div className="nl-container">
          <div className="nl-nav-inner">
            <Link to="/" className="nl-brand">
              <span className="nl-brand-icon">
                <Radio size={22} />
              </span>
              Podcast Plus Plus
            </Link>
            <div className="nl-nav-links">
              <Link to="/features">Features</Link>
              <Link to="/faq">FAQ</Link>
              <Link to="/about">About</Link>
            </div>
            <div className="nl-nav-cta">
              <Link to="/?login=1" className="nl-button-outline">
                Log In
              </Link>
              <Link to="/onboarding" className="nl-button">
                Start Free Trial
              </Link>
            </div>
          </div>
        </div>
      </nav>

      <header className="nl-section" style={{ paddingTop: '4rem', paddingBottom: '2rem' }}>
        <div className="nl-container">
          <div className="nl-section-title" style={{ maxWidth: '800px', margin: '0 auto' }}>
            <span className="nl-pill" style={{ margin: '0 auto 1.5rem' }}>
              <Sparkles size={16} /> Everything You Need
            </span>
            <h1 className="nl-hero-title" style={{ fontSize: 'clamp(2.5rem, 5vw, 4rem)', marginBottom: '1rem' }}>
              Professional Podcasting <span>Made Simple</span>
            </h1>
            <p className="nl-lead" style={{ maxWidth: '700px', margin: '0 auto' }}>
              From AI-powered editing to global distribution, Podcast Plus Plus gives you everything professional podcasters need in one intuitive platform. No technical expertise required.
            </p>
          </div>
        </div>
      </header>

      <div style={{ background: 'hsl(var(--muted) / 0.3)' }}>
        <div className="nl-container" style={{ padding: '3rem 0' }}>
          {features.map((feature, idx) => (
            <FeatureCategory key={idx} {...feature} />
          ))}
        </div>
      </div>

      <section className="nl-section nl-section-cta">
        <div className="nl-container" style={{ textAlign: 'center' }}>
          <h2 className="nl-hero-title" style={{ fontSize: 'clamp(2rem, 4vw, 3rem)', marginBottom: '1rem' }}>
            Ready to Experience the Future of Podcasting?
          </h2>
          <p className="nl-lead" style={{ maxWidth: '600px', margin: '0 auto 2rem' }}>
            Start your 14-day free trial today. No credit card required. Experience all features with no limitations.
          </p>
          <Link to="/onboarding" className="nl-button" style={{ fontSize: '1.1rem', padding: '1rem 2.5rem' }}>
            Start Free Trial
          </Link>
          <p className="text-sm text-muted-foreground" style={{ marginTop: '1.5rem' }}>
            Questions? <Link to="/faq" style={{ color: 'hsl(var(--primary))', textDecoration: 'underline' }}>Check our FAQ</Link> or <Link to="/contact" style={{ color: 'hsl(var(--primary))', textDecoration: 'underline' }}>contact us</Link>
          </p>
        </div>
      </section>

      <footer className="nl-footer">
        <div className="nl-container">
          <div className="nl-footer-grid">
            <div>
              <Link to="/" className="nl-brand" style={{ marginBottom: '1rem' }}>
                <span className="nl-brand-icon">
                  <Radio size={20} />
                </span>
                Podcast Plus Plus
              </Link>
              <p className="nl-lead" style={{ fontSize: '0.95rem' }}>
                Professional podcast hosting for the modern creator.
              </p>
            </div>
            <div>
              <p className="nl-footer-title">Product</p>
              <ul className="nl-footer-links">
                <li><Link to="/features">Features</Link></li>
                <li><Link to="/faq">FAQ</Link></li>
              </ul>
            </div>
            <div>
              <p className="nl-footer-title">Company</p>
              <ul className="nl-footer-links">
                <li><Link to="/about">About</Link></li>
                <li><Link to="/contact">Contact</Link></li>
              </ul>
            </div>
            <div>
              <p className="nl-footer-title">Legal</p>
              <ul className="nl-footer-links">
                <li><Link to="/privacy">Privacy</Link></li>
                <li><Link to="/terms">Terms</Link></li>
              </ul>
            </div>
          </div>
          <div className="nl-footer-meta">
            &copy; {new Date().getFullYear()} Podcast Plus Plus. All rights reserved.
          </div>
        </div>
      </footer>

      <style>{`
        .feature-category-section {
          margin-bottom: 4rem;
        }

        .feature-category-section:last-child {
          margin-bottom: 0;
        }

        .feature-category-header {
          display: flex;
          align-items: center;
          gap: 1.25rem;
          margin-bottom: 2rem;
        }

        .feature-category-icon {
          width: 64px;
          height: 64px;
          border-radius: 16px;
          display: grid;
          place-items: center;
        }

        .feature-category-title {
          font-size: 2rem;
          font-weight: 700;
          color: hsl(var(--foreground));
        }

        .feature-grid {
          display: grid;
          gap: 1.5rem;
          grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        }

        @media (min-width: 768px) {
          .feature-grid {
            grid-template-columns: repeat(2, 1fr);
          }
        }

        .feature-detail-card {
          background: white;
          border: 1px solid hsl(var(--border));
          border-radius: 12px;
          padding: 1.5rem;
          display: flex;
          gap: 1rem;
          transition: box-shadow 200ms ease, transform 200ms ease;
        }

        html.dark .feature-detail-card {
          background: hsl(240, 10%, 12%);
        }

        .feature-detail-card:hover {
          box-shadow: 0 8px 24px -8px hsl(var(--foreground) / 0.15);
          transform: translateY(-2px);
        }

        .feature-icon-wrapper {
          flex-shrink: 0;
          width: 48px;
          height: 48px;
          border-radius: 12px;
          background: hsl(var(--primary) / 0.12);
          color: hsl(var(--primary));
          display: grid;
          place-items: center;
        }

        .feature-card-title {
          font-size: 1.125rem;
          font-weight: 600;
          margin-bottom: 0.5rem;
          color: hsl(var(--foreground));
        }

        .feature-card-description {
          font-size: 0.95rem;
          line-height: 1.6;
          color: hsl(var(--muted-foreground));
          margin: 0;
        }
      `}</style>
    </div>
  );
}
