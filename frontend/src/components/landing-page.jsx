import React from 'react';
import NewLanding from '@/pages/NewLanding.jsx';

/**
 * Landing page entry point that renders the modern marketing experience.
 * The previous implementation now lives in `landing-page-legacy.jsx` for archival purposes.
 */
export default function LandingPage(props) {
  return <NewLanding {...props} />;
}
