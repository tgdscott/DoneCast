import React, { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import NewLanding from './NewLanding.jsx';

/**
 * Signup page that redirects to landing page with signup modal open
 * Preserves ref parameter for affiliate/referral codes
 */
export default function Signup() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  
  useEffect(() => {
    // Get ref parameter if present
    const ref = searchParams.get('ref');
    
    // Redirect to landing page, preserving ref parameter and opening signup modal
    // The landing page will detect the ref parameter and open in register mode
    const params = new URLSearchParams();
    if (ref) {
      params.set('ref', ref);
    }
    params.set('login', '1');
    
    navigate(`/?${params.toString()}`, { replace: true });
  }, [navigate, searchParams]);
  
  // Show landing page (will handle the redirect and modal opening)
  return <NewLanding />;
}

