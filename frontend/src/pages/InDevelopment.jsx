import React from 'react';
import { Link } from 'react-router-dom';
import { Hammer, Sparkles } from 'lucide-react';
import './new-landing.css';

export default function InDevelopment() {
  return (
    <div className="new-landing" style={{ minHeight: '100vh', display: 'flex', alignItems: 'center' }}>
      <div className="nl-container" style={{ textAlign: 'center', padding: '5rem 0' }}>
        <div className="nl-pill" style={{ justifyContent: 'center', marginBottom: '1.5rem' }}>
          <Sparkles size={16} /> New experiences incoming
        </div>
        <h1 className="nl-hero-title" style={{ fontSize: 'clamp(2.2rem, 4vw, 3.2rem)', marginBottom: '1rem' }}>
          We&apos;re still building this area
        </h1>
        <p className="nl-lead" style={{ margin: '0 auto 2.5rem', maxWidth: '560px' }}>
          Thanks for your interest! Our team is actively polishing this part of the product. Sign up for the free trial and
          we&apos;ll notify you the moment it&apos;s ready.
        </p>
        <div className="nl-hero-actions" style={{ justifyContent: 'center' }}>
          <Link to="/onboarding" className="nl-button" style={{ fontSize: '1rem', padding: '0.85rem 2.1rem' }}>
            Start Free Trial
          </Link>
          <Link to="/" className="nl-button-outline" style={{ fontSize: '1rem', padding: '0.85rem 2.1rem' }}>
            Back to Home
          </Link>
        </div>
        <div
          className="nl-card"
          style={{
            margin: '3rem auto 0',
            maxWidth: '520px',
            display: 'flex',
            alignItems: 'center',
            gap: '1.25rem',
            justifyContent: 'center',
          }}
        >
          <div
            className="nl-card-icon"
            style={{
              width: '56px',
              height: '56px',
              background: 'hsl(var(--primary) / 0.16)',
              color: 'hsl(var(--primary))',
            }}
          >
            <Hammer size={26} />
          </div>
          <div style={{ textAlign: 'left' }}>
            <p className="font-semibold">Want early access?</p>
            <p className="nl-lead" style={{ fontSize: '0.95rem' }}>
              Drop us a line after you onboard—we&apos;re inviting a handful of customers to try the latest tools.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
