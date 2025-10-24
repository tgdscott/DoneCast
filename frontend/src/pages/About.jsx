import React from 'react';
import { Link } from 'react-router-dom';
import { Radio, Sparkles, Heart, Target, Lightbulb, Users, Zap, Globe } from 'lucide-react';
import '../pages/new-landing.css';

const values = [
  {
    title: 'Democratizing Creativity',
    description: 'We believe everyone has a voice worth sharing. Technology should empower creators, not create barriers. Our mission is to make professional podcasting accessible to anyone, regardless of technical skill or budget.',
    icon: <Users size={28} />,
    color: 'primary',
  },
  {
    title: 'Innovation That Matters',
    description: 'We don\'t add AI features just because we can. Every feature solves a real problem creators face. Our patent-pending technology exists to save you time, money, and frustration.',
    icon: <Lightbulb size={28} />,
    color: 'secondary',
  },
  {
    title: 'Quality Without Compromise',
    description: 'Simple doesn\'t mean limited. Our platform is easy enough for beginners but powerful enough for professionals. We never sacrifice quality for convenience—you get both.',
    icon: <Target size={28} />,
    color: 'accent',
  },
  {
    title: 'Creator-First Philosophy',
    description: 'Every decision starts with one question: "Does this help creators?" Your success is our success. Your feedback shapes our roadmap. You own your content, always.',
    icon: <Heart size={28} />,
    color: 'primary',
  },
];

const milestones = [
  {
    year: '2024',
    title: 'The Vision',
    description: 'Frustrated by expensive, complicated podcast tools, we set out to build something better. Something anyone could use.',
  },
  {
    year: '2025',
    title: 'Patent-Pending Technology',
    description: 'We invented real-time AI editing that processes audio as you record. Technology that literally didn\'t exist before.',
  },
  {
    year: 'Today',
    title: 'Empowering Creators',
    description: 'Thousands of creators are using Podcast Plus Plus to share their voices with the world. From first-timers to seasoned pros.',
  },
  {
    year: 'Tomorrow',
    title: 'The Future',
    description: 'We\'re just getting started. More AI features, better tools, deeper insights—all focused on making you successful.',
  },
];

function ValueCard({ title, description, icon, color }) {
  return (
    <div className="about-value-card">
      <div
        className="about-value-icon"
        style={{
          background: `hsl(var(--${color}) / 0.14)`,
          color: `hsl(var(--${color}))`,
        }}
      >
        {icon}
      </div>
      <h3 className="about-value-title">{title}</h3>
      <p className="about-value-description">{description}</p>
    </div>
  );
}

function MilestoneCard({ year, title, description }) {
  return (
    <div className="about-milestone">
      <div className="about-milestone-year">{year}</div>
      <div>
        <h3 className="about-milestone-title">{title}</h3>
        <p className="about-milestone-description">{description}</p>
      </div>
    </div>
  );
}

export default function About() {
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

      <header className="nl-section" style={{ paddingTop: '4rem', paddingBottom: '3rem' }}>
        <div className="nl-container">
          <div className="nl-section-title" style={{ maxWidth: '800px', margin: '0 auto' }}>
            <span className="nl-pill" style={{ margin: '0 auto 1.5rem' }}>
              <Heart size={16} /> Our Story
            </span>
            <h1 className="nl-hero-title" style={{ fontSize: 'clamp(2.5rem, 5vw, 4rem)', marginBottom: '1rem' }}>
              Making Professional Podcasting <span>Accessible to Everyone</span>
            </h1>
            <p className="nl-lead" style={{ maxWidth: '700px', margin: '0 auto' }}>
              We're on a mission to democratize podcasting. Everyone has a story worth telling, a message worth sharing, or knowledge worth teaching. The only thing standing in the way? Complicated, expensive tools that require technical expertise most people don't have.
            </p>
          </div>
        </div>
      </header>

      <section className="nl-section nl-section-muted">
        <div className="nl-container">
          <div style={{ maxWidth: '800px', margin: '0 auto' }}>
            <h2 className="nl-hero-title" style={{ fontSize: 'clamp(2rem, 4vw, 3rem)', marginBottom: '2rem', textAlign: 'center' }}>
              The <span>Problem</span>
            </h2>
            <div className="about-story-text">
              <p>
                Traditional podcast production is a nightmare. Record your audio, export it, import it into an audio editor, spend hours removing filler words and awkward pauses, export again, upload to a hosting platform, manually distribute to podcast directories, write show notes, create artwork... it's exhausting.
              </p>
              <p>
                The alternative? Hire an editor ($100+ per episode), a distribution service ($20-50/month), and spend weeks learning complicated software. For most aspiring podcasters, it's simply too much. Great ideas never get shared because the barrier to entry is too high.
              </p>
              <p>
                <strong>We said: there has to be a better way.</strong>
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="nl-section">
        <div className="nl-container">
          <div style={{ maxWidth: '800px', margin: '0 auto' }}>
            <h2 className="nl-hero-title" style={{ fontSize: 'clamp(2rem, 4vw, 3rem)', marginBottom: '2rem', textAlign: 'center' }}>
              Our <span>Solution</span>
            </h2>
            <div className="about-story-text">
              <p>
                We built Podcast Plus Plus from the ground up to solve these problems. Our patent-pending AI technology processes audio in real-time as you record. It removes filler words, eliminates awkward pauses, balances audio levels, and even understands spoken editing commands.
              </p>
              <p>
                When you're done recording, your episode is already edited. One click publishes it to all major podcast platforms. Show notes? Generated automatically. RSS feed? Updated instantly. Distribution? Handled.
              </p>
              <p>
                <strong>What used to take hours now takes minutes. What used to cost hundreds per episode now costs a simple monthly subscription.</strong>
              </p>
              <p>
                But here's what matters most: we didn't just make it faster and cheaper. We made it <em>easy</em>. So easy that your grandparents could start a podcast. So intuitive that you don't need to watch tutorials or read manuals. Just hit record and start talking.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="nl-section nl-section-alt">
        <div className="nl-container">
          <h2 className="nl-hero-title" style={{ fontSize: 'clamp(2rem, 4vw, 3rem)', marginBottom: '3rem', textAlign: 'center' }}>
            Our <span>Values</span>
          </h2>
          <div className="about-values-grid">
            {values.map((value, idx) => (
              <ValueCard key={idx} {...value} />
            ))}
          </div>
        </div>
      </section>

      <section className="nl-section">
        <div className="nl-container">
          <h2 className="nl-hero-title" style={{ fontSize: 'clamp(2rem, 4vw, 3rem)', marginBottom: '3rem', textAlign: 'center' }}>
            Our <span>Journey</span>
          </h2>
          <div className="about-timeline">
            {milestones.map((milestone, idx) => (
              <MilestoneCard key={idx} {...milestone} />
            ))}
          </div>
        </div>
      </section>

      <section className="nl-section nl-section-highlight">
        <div className="nl-container">
          <div className="about-stats-grid">
            <div className="about-stat">
              <div className="about-stat-icon">
                <Sparkles size={32} />
              </div>
              <div className="about-stat-number">Patent-Pending</div>
              <div className="about-stat-label">AI Technology</div>
            </div>
            <div className="about-stat">
              <div className="about-stat-icon">
                <Zap size={32} />
              </div>
              <div className="about-stat-number">10x Faster</div>
              <div className="about-stat-label">Than Traditional Editing</div>
            </div>
            <div className="about-stat">
              <div className="about-stat-icon">
                <Globe size={32} />
              </div>
              <div className="about-stat-number">20+ Platforms</div>
              <div className="about-stat-label">Automatic Distribution</div>
            </div>
            <div className="about-stat">
              <div className="about-stat-icon">
                <Users size={32} />
              </div>
              <div className="about-stat-number">Any Skill Level</div>
              <div className="about-stat-label">Beginner to Pro</div>
            </div>
          </div>
        </div>
      </section>

      <section className="nl-section nl-section-cta">
        <div className="nl-container" style={{ textAlign: 'center' }}>
          <h2 className="nl-hero-title" style={{ fontSize: 'clamp(2rem, 4vw, 3rem)', marginBottom: '1rem' }}>
            Ready to Start Your Podcasting Journey?
          </h2>
          <p className="nl-lead" style={{ maxWidth: '600px', margin: '0 auto 2rem' }}>
            Join thousands of creators who are sharing their voices with the world. Your story deserves to be heard.
          </p>
          <Link to="/onboarding" className="nl-button" style={{ fontSize: '1.1rem', padding: '1rem 2.5rem' }}>
            Start Free Trial
          </Link>
          <p className="text-sm text-muted-foreground" style={{ marginTop: '1.5rem' }}>
            14-day free trial • No credit card required • Cancel anytime
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

      <style jsx>{`
        .about-story-text {
          font-size: 1.05rem;
          line-height: 1.8;
          color: hsl(var(--foreground));
        }

        .about-story-text p {
          margin-bottom: 1.5rem;
        }

        .about-story-text strong {
          color: hsl(var(--primary));
          font-weight: 600;
        }

        .about-values-grid {
          display: grid;
          gap: 2rem;
          grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        }

        @media (min-width: 768px) {
          .about-values-grid {
            grid-template-columns: repeat(2, 1fr);
          }
        }

        .about-value-card {
          background: white;
          border: 1px solid hsl(var(--border));
          border-radius: 16px;
          padding: 2rem;
          text-align: center;
        }

        html.dark .about-value-card {
          background: hsl(240, 10%, 12%);
        }

        .about-value-icon {
          width: 64px;
          height: 64px;
          border-radius: 16px;
          display: grid;
          place-items: center;
          margin: 0 auto 1.5rem;
        }

        .about-value-title {
          font-size: 1.25rem;
          font-weight: 700;
          margin-bottom: 0.75rem;
          color: hsl(var(--foreground));
        }

        .about-value-description {
          font-size: 1rem;
          line-height: 1.7;
          color: hsl(var(--muted-foreground));
        }

        .about-timeline {
          max-width: 800px;
          margin: 0 auto;
          position: relative;
          padding-left: 2rem;
        }

        .about-timeline::before {
          content: '';
          position: absolute;
          left: 0;
          top: 0;
          bottom: 0;
          width: 2px;
          background: hsl(var(--primary) / 0.3);
        }

        .about-milestone {
          position: relative;
          margin-bottom: 3rem;
          padding-left: 2rem;
        }

        .about-milestone::before {
          content: '';
          position: absolute;
          left: -2rem;
          top: 0.5rem;
          width: 12px;
          height: 12px;
          border-radius: 50%;
          background: hsl(var(--primary));
          border: 3px solid hsl(var(--background));
          transform: translateX(-5px);
        }

        .about-milestone-year {
          font-size: 0.9rem;
          font-weight: 700;
          color: hsl(var(--primary));
          text-transform: uppercase;
          letter-spacing: 0.05em;
          margin-bottom: 0.5rem;
        }

        .about-milestone-title {
          font-size: 1.5rem;
          font-weight: 700;
          margin-bottom: 0.5rem;
          color: hsl(var(--foreground));
        }

        .about-milestone-description {
          font-size: 1rem;
          line-height: 1.7;
          color: hsl(var(--muted-foreground));
        }

        .about-stats-grid {
          display: grid;
          gap: 2rem;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        }

        @media (min-width: 768px) {
          .about-stats-grid {
            grid-template-columns: repeat(4, 1fr);
          }
        }

        .about-stat {
          text-align: center;
        }

        .about-stat-icon {
          width: 64px;
          height: 64px;
          margin: 0 auto 1rem;
          border-radius: 16px;
          background: hsl(var(--primary) / 0.12);
          color: hsl(var(--primary));
          display: grid;
          place-items: center;
        }

        .about-stat-number {
          font-size: 2rem;
          font-weight: 700;
          color: hsl(var(--foreground));
          margin-bottom: 0.5rem;
        }

        .about-stat-label {
          font-size: 0.95rem;
          color: hsl(var(--muted-foreground));
        }
      `}</style>
    </div>
  );
}
