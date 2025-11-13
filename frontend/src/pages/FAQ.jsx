import React from 'react';
import { Link } from 'react-router-dom';
import { Radio, ChevronDown } from 'lucide-react';
import '../pages/new-landing.css';

const faqs = [
  {
    category: 'Getting Started',
    questions: [
      {
        q: 'Do I need any technical experience to use Podcast Plus Plus?',
        a: 'Absolutely not! We designed Podcast Plus Plus for everyone—from complete beginners to seasoned pros. If you can record a voice memo on your phone, you can create a professional podcast with our platform. Our AI handles the technical complexity behind the scenes.',
      },
      {
        q: 'How long does it take to publish my first episode?',
        a: 'Most users publish their first episode within 30 minutes of signing up. Record your audio, let our AI process it, review the results, and publish with one click. It\'s that simple.',
      },
      {
        q: 'What equipment do I need?',
        a: 'Just a microphone and a computer. You can start with your laptop\'s built-in mic, though we recommend a USB microphone (starting around $50) for better audio quality. No expensive audio interfaces, soundproofing, or studio required.',
      },
      {
        q: 'Can I try it before committing?',
        a: 'Yes! We offer a 14-day free trial with full access to all features. No credit card required to start. Experience everything the platform can do before making any decision.',
      },
    ],
  },
  {
    category: 'Features & Capabilities',
    questions: [
      {
        q: 'What makes the AI editing different from other platforms?',
        a: 'Our patent-pending AI technology processes audio in real-time as you record, not just afterward. It removes filler words, awkward pauses, and audio issues automatically. You can even speak editing commands like "insert intro here" and the AI understands and executes them. This technology literally doesn\'t exist anywhere else.',
      },
      {
        q: 'Can I still edit manually if I want to?',
        a: 'Absolutely! While our AI handles most editing automatically, you have full manual control through our intuitive editor. Trim clips, adjust volumes, add music, insert segments—whatever you need. The AI just handles the tedious work so you can focus on creative decisions.',
      },
      {
        q: 'Where will my podcast be available?',
        a: 'One-click distribution to all major platforms: Spotify, Apple Podcasts, Google Podcasts, Amazon Music, Stitcher, TuneIn, iHeartRadio, and 20+ other directories. Your RSS feed is automatically generated and updated with each new episode.',
      },
      {
        q: 'Is there a limit on episode length or file size?',
        a: 'No artificial limits! Upload episodes of any length. Our platform handles everything from 5-minute daily updates to 3-hour interview marathons. You get unlimited storage and bandwidth.',
      },
      {
        q: 'Can I have multiple podcasts?',
        a: 'Yes! Depending on your plan, you can manage multiple shows from one account. Perfect for creators with different topics or formats.',
      },
      {
        q: 'Do you support video podcasts?',
        a: 'Currently, we focus on audio podcasting where our AI technology excels. Video podcast support is on our roadmap based on user demand.',
      },
    ],
  },
  {
    category: 'Pricing & Plans',
    questions: [
      {
        q: 'What happens after my free trial?',
        a: 'You\'ll be prompted to choose a plan that fits your needs. If you don\'t select a plan, your account remains active but publishing is paused until you subscribe. All your content and settings are preserved.',
      },
      {
        q: 'Can I change plans later?',
        a: 'Yes, anytime! Upgrade or downgrade between plans as your needs change. Upgrades take effect immediately, while downgrades apply at your next billing cycle.',
      },
      {
        q: 'What payment methods do you accept?',
        a: 'We accept all major credit cards (Visa, MasterCard, American Express, Discover) through our secure payment processor Stripe. We also support PayPal and certain regional payment methods.',
      },
      {
        q: 'Are there any hidden fees?',
        a: 'Never. The price you see is the price you pay. No setup fees, no bandwidth charges, no storage fees, no surprise costs. Just straightforward monthly or annual billing.',
      },
      {
        q: 'What\'s your refund policy?',
        a: 'We offer a 30-day money-back guarantee on annual plans. If you\'re not satisfied within the first 30 days, we\'ll refund your payment in full. Monthly subscriptions can be cancelled anytime with no cancellation fees.',
      },
    ],
  },
  {
    category: 'Credits & Billing',
    questions: [
      {
        q: 'How does the credit system work?',
        a: 'We like to keep things simple and transparent — you always know what you\'re getting and what it costs. Every second of audio you record or upload uses 1 credit. When you\'re ready to assemble your final episode, final audio assembly costs 3 credits per second — covering your intros, outros, and all the polishing that makes your episode shine.',
      },
      {
        q: 'How many credits do I get with each plan?',
        a: 'Starter: 28,800 credits = about 2 hours of finished audio. Creator: 72,000 credits = about 5 hours. Pro: 172,800 credits = about 12 hours. Executive: 288,000 credits = about 20 hours.',
      },
      {
        q: 'What is premium processing and how much does it cost?',
        a: 'Our premium processing automatically upgrades lower-quality recordings (like from webcams or phones) to studio-quality sound for just 1 extra credit per second.',
      },
      {
        q: 'How much do optional features cost?',
        a: 'AI Titles, Descriptions & Tags: 1–3 credits each — perfect for quick content creation. Intern Feature: 1 credit per answer — your built-in helper. Text-to-Speech: 12–15 credits per second — natural, studio-grade voices for intros, outros, or responses.',
      },
      {
        q: 'Can I get credits back if I delete an episode?',
        a: 'Yes! You can undo and get credits back: Delete within 24 hours → refund of 2 out of every 3 credits. Delete within 7 days → refund of 1 out of every 3 credits. After 7 days, refunds close automatically.',
      },
      {
        q: 'What if something goes wrong with my subscription?',
        a: 'We\'re still in alpha, which means we\'re improving fast and keeping things fair. If something goes wrong, just request a refund in your subscription page — we\'ll make it right.',
      },
    ],
  },
  {
    category: 'Technical Details',
    questions: [
      {
        q: 'What audio formats do you support?',
        a: 'We accept MP3, WAV, M4A, FLAC, and most common audio formats. Our system automatically converts and optimizes files for podcast distribution.',
      },
      {
        q: 'How do you ensure audio quality?',
        a: 'Our AI automatically normalizes audio levels, removes background noise, and applies professional mastering. Episodes are encoded at industry-standard 128kbps for distribution, balancing quality with download speed.',
      },
      {
        q: 'Is my content secure?',
        a: 'Yes. All files are encrypted in transit and at rest. We use Google Cloud Storage for reliable, secure hosting. We never share or sell your content. You retain full ownership and can export or delete everything at any time.',
      },
      {
        q: 'Can I import an existing podcast?',
        a: 'Yes! We can import your existing podcast from any platform. Just provide your current RSS feed or episode files, and we\'ll migrate everything while preserving your episode history and metadata.',
      },
      {
        q: 'Do you provide analytics?',
        a: 'Yes! Track downloads, listener locations, popular episodes, listening platforms, and audience growth over time. We integrate with industry-standard analytics providers for certified IAB stats.',
      },
    ],
  },
  {
    category: 'Support & Community',
    questions: [
      {
        q: 'What kind of support do you offer?',
        a: 'All users get email support with responses within 24 hours. Paid subscribers get priority support. We also have comprehensive guides, video tutorials, and an active community forum.',
      },
      {
        q: 'Can you help me plan my podcast?',
        a: 'While we focus on the technical platform, we provide extensive guides on podcast planning, content strategy, audience building, and best practices. Our AI assistant "Mike" can also provide personalized suggestions.',
      },
      {
        q: 'Do you offer training or onboarding?',
        a: 'Every new user goes through our interactive onboarding wizard that walks you through creating your first episode. We also offer optional video tutorials and written guides for every feature.',
      },
    ],
  },
];

function FAQItem({ question, answer }) {
  const [isOpen, setIsOpen] = React.useState(false);

  return (
    <div className="faq-item">
      <button
        className="faq-question"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
      >
        <span>{question}</span>
        <ChevronDown
          size={20}
          className="faq-chevron"
          style={{
            transform: isOpen ? 'rotate(180deg)' : 'rotate(0)',
            transition: 'transform 200ms ease',
          }}
        />
      </button>
      {isOpen && (
        <div className="faq-answer">
          <p>{answer}</p>
        </div>
      )}
    </div>
  );
}

function FAQCategory({ category, questions }) {
  return (
    <div className="faq-category">
      <h2 className="faq-category-title">{category}</h2>
      <div className="faq-list">
        {questions.map((faq, idx) => (
          <FAQItem key={idx} question={faq.q} answer={faq.a} />
        ))}
      </div>
    </div>
  );
}

export default function FAQ() {
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

      <div className="nl-section" style={{ paddingTop: '4rem', paddingBottom: '4rem' }}>
        <div className="nl-container">
          <div className="nl-section-title" style={{ maxWidth: '700px', margin: '0 auto 3rem' }}>
            <h1 className="nl-hero-title" style={{ fontSize: 'clamp(2.5rem, 5vw, 4rem)', marginBottom: '1rem' }}>
              Frequently Asked <span>Questions</span>
            </h1>
            <p className="nl-lead">
              Everything you need to know about Podcast Plus Plus. Can't find your answer? <Link to="/contact" style={{ color: 'hsl(var(--primary))', textDecoration: 'underline' }}>Contact us</Link> and we'll help.
            </p>
          </div>

          <div style={{ maxWidth: '900px', margin: '0 auto' }}>
            {faqs.map((category, idx) => (
              <FAQCategory
                key={idx}
                category={category.category}
                questions={category.questions}
              />
            ))}
          </div>

          <div className="nl-cta" style={{ marginTop: '4rem' }}>
            <h3 style={{ fontSize: '1.5rem', marginBottom: '1rem', fontWeight: 600 }}>
              Still have questions?
            </h3>
            <p className="nl-lead" style={{ marginBottom: '1.5rem' }}>
              We're here to help. Reach out and we'll get back to you within 24 hours.
            </p>
            <Link to="/contact" className="nl-button">
              Contact Support
            </Link>
          </div>
        </div>
      </div>

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
        .faq-category {
          margin-bottom: 3rem;
        }

        .faq-category-title {
          font-size: 1.75rem;
          font-weight: 700;
          margin-bottom: 1.5rem;
          color: hsl(var(--foreground));
        }

        .faq-list {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }

        .faq-item {
          background: white;
          border: 1px solid hsl(var(--border));
          border-radius: 12px;
          overflow: hidden;
        }

        html.dark .faq-item {
          background: hsl(240, 10%, 12%);
        }

        .faq-question {
          width: 100%;
          padding: 1.25rem 1.5rem;
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 1rem;
          background: none;
          border: none;
          text-align: left;
          font-size: 1.05rem;
          font-weight: 600;
          color: hsl(var(--foreground));
          cursor: pointer;
          transition: background 200ms ease;
        }

        .faq-question:hover {
          background: hsl(var(--muted) / 0.3);
        }

        .faq-answer {
          padding: 0 1.5rem 1.25rem 1.5rem;
          color: hsl(var(--muted-foreground));
          line-height: 1.7;
        }

        .faq-answer p {
          margin: 0;
        }

        .faq-chevron {
          flex-shrink: 0;
          color: hsl(var(--primary));
        }
      `}</style>
    </div>
  );
}
