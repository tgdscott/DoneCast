import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';
import { setWarmupCallbacks } from '@/lib/apiClient';

const WarmupContext = createContext(null);

export function WarmupProvider({ children }) {
  const [isWarmingUp, setIsWarmingUp] = useState(false);
  const activeRequestsRef = useRef(new Set());
  const timeoutRefsRef = useRef(new Map());

  const startRequest = useCallback((requestId) => {
    activeRequestsRef.current.add(requestId);
    
    // Create a timeout for this specific request
    const timeoutId = setTimeout(() => {
      // Only show warmup if this request is still active
      if (activeRequestsRef.current.has(requestId)) {
        setIsWarmingUp(true);
      }
      timeoutRefsRef.current.delete(requestId);
    }, 3000);
    
    timeoutRefsRef.current.set(requestId, timeoutId);
  }, []);

  const endRequest = useCallback((requestId) => {
    // Clear the timeout for this request
    const timeoutId = timeoutRefsRef.current.get(requestId);
    if (timeoutId) {
      clearTimeout(timeoutId);
      timeoutRefsRef.current.delete(requestId);
    }
    
    // Remove from active requests
    activeRequestsRef.current.delete(requestId);
    
    // If no more active requests, hide the warmup loader
    if (activeRequestsRef.current.size === 0) {
      setIsWarmingUp(false);
    }
  }, []);

  // Register callbacks with API client on mount
  useEffect(() => {
    setWarmupCallbacks(startRequest, endRequest);
    
    // Cleanup on unmount
    return () => {
      setWarmupCallbacks(null, null);
      // Clear all timeouts
      timeoutRefsRef.current.forEach((timeoutId) => clearTimeout(timeoutId));
      timeoutRefsRef.current.clear();
      activeRequestsRef.current.clear();
    };
  }, [startRequest, endRequest]);

  return (
    <WarmupContext.Provider value={{ isWarmingUp, startRequest, endRequest }}>
      {children}
    </WarmupContext.Provider>
  );
}

export function useWarmup() {
  const context = useContext(WarmupContext);
  if (!context) {
    throw new Error('useWarmup must be used within WarmupProvider');
  }
  return context;
}

