/**
 * Enhanced Bug Report Context Collector
 * 
 * Automatically captures technical context when users report bugs.
 * Reduces back-and-forth by collecting browser, console, and network info upfront.
 */

/**
 * Capture all available technical context for bug reports
 * @returns {Object} Comprehensive context object
 */
export function captureBugContext() {
  const context = {};
  
  // 1. Browser & Device Info
  try {
    const ua = navigator.userAgent;
    context.user_agent = ua;
    
    // Parse user agent for readable info
    const browser = detectBrowser(ua);
    const os = detectOS(ua);
    const device = detectDevice();
    
    context.browser_info = `${browser} on ${os} (${device})`;
  } catch (e) {
    context.browser_info = 'Unable to detect';
  }
  
  // 2. Viewport & Screen Info
  try {
    context.viewport_size = `${window.innerWidth}x${window.innerHeight}`;
    context.screen_size = `${screen.width}x${screen.height}`;
    context.pixel_ratio = window.devicePixelRatio || 1;
  } catch (e) {
    // Ignore
  }
  
  // 3. Current Page Info
  try {
    context.page_url = window.location.pathname + window.location.search;
    context.page_title = document.title;
    context.referrer = document.referrer || 'Direct';
  } catch (e) {
    // Ignore
  }
  
  // 4. Console Errors (captured from global error handler)
  try {
    const errors = window.__PPP_CONSOLE_ERRORS__ || [];
    if (errors.length > 0) {
      context.console_errors = JSON.stringify(errors.slice(-10)); // Last 10 errors
    }
  } catch (e) {
    // Ignore
  }
  
  // 5. Network Errors (captured from global fetch interceptor)
  try {
    const networkErrors = window.__PPP_NETWORK_ERRORS__ || [];
    if (networkErrors.length > 0) {
      context.network_errors = JSON.stringify(networkErrors.slice(-5)); // Last 5 network failures
    }
  } catch (e) {
    // Ignore
  }
  
  // 6. LocalStorage Context (auth status, feature flags)
  try {
    const relevantKeys = ['auth_token', 'user_id', 'last_podcast', 'last_episode', 'onboarding_completed'];
    const localData = {};
    
    relevantKeys.forEach(key => {
      const value = localStorage.getItem(key);
      if (value) {
        // Don't send full tokens, just presence
        if (key === 'auth_token') {
          localData[key] = value ? `present (${value.length} chars)` : 'missing';
        } else {
          localData[key] = value;
        }
      }
    });
    
    if (Object.keys(localData).length > 0) {
      context.local_storage_data = JSON.stringify(localData);
    }
  } catch (e) {
    // Ignore
  }
  
  // 7. Performance Metrics (if page is slow)
  try {
    if (window.performance && window.performance.timing) {
      const timing = window.performance.timing;
      const loadTime = timing.loadEventEnd - timing.navigationStart;
      const domReady = timing.domContentLoadedEventEnd - timing.navigationStart;
      
      context.performance = JSON.stringify({
        load_time_ms: loadTime,
        dom_ready_ms: domReady,
        current_memory_mb: (performance.memory?.usedJSHeapSize || 0) / 1024 / 1024,
      });
    }
  } catch (e) {
    // Ignore
  }
  
  // 8. Feature Flags (from window global if set)
  try {
    if (window.__FEATURE_FLAGS__) {
      context.feature_flags = JSON.stringify(window.__FEATURE_FLAGS__);
    }
  } catch (e) {
    // Ignore
  }
  
  return context;
}

/**
 * Simple browser detection from user agent
 */
function detectBrowser(ua) {
  if (/edg/i.test(ua)) return 'Edge';
  if (/chrome|chromium|crios/i.test(ua)) return 'Chrome';
  if (/firefox|fxios/i.test(ua)) return 'Firefox';
  if (/safari/i.test(ua) && !/chrome/i.test(ua)) return 'Safari';
  if (/opr\//i.test(ua)) return 'Opera';
  return 'Unknown';
}

/**
 * Simple OS detection from user agent
 */
function detectOS(ua) {
  if (/windows phone/i.test(ua)) return 'Windows Phone';
  if (/win/i.test(ua)) return 'Windows';
  if (/android/i.test(ua)) return 'Android';
  if (/iphone|ipad|ipod/i.test(ua)) return 'iOS';
  if (/mac/i.test(ua)) return 'macOS';
  if (/linux/i.test(ua)) return 'Linux';
  return 'Unknown';
}

/**
 * Simple device type detection
 */
function detectDevice() {
  const ua = navigator.userAgent;
  if (/(tablet|ipad|playbook|silk)|(android(?!.*mobi))/i.test(ua)) {
    return 'Tablet';
  }
  if (/Mobile|Android|iP(hone|od)|IEMobile|BlackBerry|Kindle|Silk-Accelerated|(hpw|web)OS|Opera M(obi|ini)/.test(ua)) {
    return 'Mobile';
  }
  return 'Desktop';
}

/**
 * Initialize global error and network interceptors
 * Call this once at app startup
 */
export function initBugReportCapture() {
  // Capture console errors
  if (!window.__PPP_CONSOLE_ERRORS__) {
    window.__PPP_CONSOLE_ERRORS__ = [];
    
    const originalConsoleError = console.error;
    console.error = function(...args) {
      window.__PPP_CONSOLE_ERRORS__.push({
        timestamp: new Date().toISOString(),
        message: args.map(a => String(a)).join(' '),
      });
      
      // Keep only last 20 errors to prevent memory issues
      if (window.__PPP_CONSOLE_ERRORS__.length > 20) {
        window.__PPP_CONSOLE_ERRORS__ = window.__PPP_CONSOLE_ERRORS__.slice(-20);
      }
      
      originalConsoleError.apply(console, args);
    };
  }
  
  // Capture network errors
  if (!window.__PPP_NETWORK_ERRORS__) {
    window.__PPP_NETWORK_ERRORS__ = [];
    
    // Intercept fetch failures
    const originalFetch = window.fetch;
    window.fetch = function(...args) {
      const url = args[0];
      
      return originalFetch.apply(this, args).catch(error => {
        window.__PPP_NETWORK_ERRORS__.push({
          timestamp: new Date().toISOString(),
          url: String(url),
          error: error.message,
        });
        
        // Keep only last 10 network errors
        if (window.__PPP_NETWORK_ERRORS__.length > 10) {
          window.__PPP_NETWORK_ERRORS__ = window.__PPP_NETWORK_ERRORS__.slice(-10);
        }
        
        throw error; // Re-throw to maintain normal error handling
      });
    };
  }
  
  // Capture unhandled promise rejections
  window.addEventListener('unhandledrejection', (event) => {
    window.__PPP_CONSOLE_ERRORS__.push({
      timestamp: new Date().toISOString(),
      message: `Unhandled Promise Rejection: ${event.reason}`,
      type: 'unhandled_rejection',
    });
  });
  
  // Capture global errors
  window.addEventListener('error', (event) => {
    window.__PPP_CONSOLE_ERRORS__.push({
      timestamp: new Date().toISOString(),
      message: `${event.message} at ${event.filename}:${event.lineno}:${event.colno}`,
      type: 'global_error',
    });
  });
}

/**
 * Create screenshot (using html2canvas if available)
 * @returns {Promise<string|null>} Base64 data URL or null if not available
 */
export async function captureScreenshot() {
  try {
    // Try to use html2canvas if available
    if (window.html2canvas) {
      const canvas = await window.html2canvas(document.body, {
        logging: false,
        useCORS: true,
        scale: 0.5, // Reduce file size
      });
      return canvas.toDataURL('image/jpeg', 0.7); // 70% quality
    }
    
    // Try to use modern Screenshot API (if supported)
    if (navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia) {
      // This would require user permission - maybe too intrusive for automatic capture
      // Keep this as a manual option only
      return null;
    }
    
    return null;
  } catch (e) {
    console.warn('[BugCapture] Screenshot failed:', e);
    return null;
  }
}

/**
 * Prompt user for reproduction steps
 * @returns {Promise<string|null>} User-provided steps or null if cancelled
 */
export function promptForReproductionSteps() {
  return new Promise((resolve) => {
    const steps = prompt(
      'Optional: Help us reproduce this issue\n\n' +
      'What were you trying to do when this happened?\n' +
      'Example:\n' +
      '1. Clicked "Upload Audio"\n' +
      '2. Selected a 50MB file\n' +
      '3. Upload started but then failed'
    );
    
    resolve(steps ? steps.trim() : null);
  });
}
