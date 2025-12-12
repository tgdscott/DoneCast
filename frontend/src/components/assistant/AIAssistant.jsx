/**
 * AI Assistant Chat Widget
 * 
 * Provides interactive AI assistance with:
 * - Reactive help (user asks questions)
 * - Proactive guidance (AI offers help when stuck)
 * - Bug reporting and feedback collection
 * - Step-by-step onboarding for new users
 */

import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { MessageCircle, X, Send, Minimize2, Maximize2, HelpCircle, AlertCircle, Lightbulb } from 'lucide-react';
import { Button } from '../ui/button';
import { makeApi } from '../../lib/apiClient';
import { captureBugContext } from '../../lib/bugReportCapture';

export default function AIAssistant({
  token,
  user,
  onboardingMode = false,
  currentStep = null,
  currentStepData = null,
  currentPage = null, // e.g., 'dashboard', 'episodes', etc.
  onRestartTooltips = null, // callback to restart page-specific tooltips
}) {
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [isPoppedOut, setIsPoppedOut] = useState(false);
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId] = useState(() => `session_${Date.now()}_${Math.random()}`);
  const [guidanceStatus, setGuidanceStatus] = useState(null);
  const [proactiveHelp, setProactiveHelp] = useState(null);
  const [popupWindow, setPopupWindow] = useState(null);

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const pageStartTime = useRef(Date.now());
  const actionsAttempted = useRef([]);
  const errorsEncountered = useRef([]);
  const lastProactiveStep = useRef(null);
  const hasShownIntro = useRef(false);
  const [isDesktop, setIsDesktop] = useState(false);

  // Track reminder timing for exponential backoff (#1)
  const lastDismissTime = useRef(null);
  const currentReminderInterval = useRef(120000); // Start at 2 minutes (120000ms)

  // Detect if we're on desktop (screen width >= 768px)
  useEffect(() => {
    const checkDesktop = () => {
      setIsDesktop(window.innerWidth >= 768);
    };
    checkDesktop();
    window.addEventListener('resize', checkDesktop);
    return () => window.removeEventListener('resize', checkDesktop);
  }, []);

  // Clean up popup window on unmount
  useEffect(() => {
    return () => {
      if (popupWindow && !popupWindow.closed) {
        popupWindow.close();
      }
    };
  }, [popupWindow]);

  // Clear proactive help reminder when user navigates to a different page
  useEffect(() => {
    // Reset page tracking when currentPage changes
    pageStartTime.current = Date.now();
    actionsAttempted.current = [];
    errorsEncountered.current = [];

    // Clear any active reminder bubble since user is now on a new screen
    setProactiveHelp(null);
  }, [currentPage]); // Re-run whenever the user navigates to a different page

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load guidance status on mount
  useEffect(() => {
    if (token && user) {
      loadGuidanceStatus();
    }
  }, [token, user]);

  // Check for proactive help periodically - ONLY shows speech bubble, doesn't auto-open
  useEffect(() => {
    if (!token || !user) return;

    const checkInterval = setInterval(() => {
      checkProactiveHelp(); // This only sets proactiveHelp state, doesn't open chat
    }, currentReminderInterval.current); // Use dynamic interval with exponential backoff

    return () => clearInterval(checkInterval);
  }, [token, user, currentReminderInterval.current]); // Added currentReminderInterval to dependencies

  // Show welcome message when chat first opens (introduce Mike!)
  useEffect(() => {
    // Only show introduction once when chat is opened
    if (isOpen && !hasShownIntro.current && user) {
      hasShownIntro.current = true;

      const introMessage = onboardingMode
        ? `Hey ${user?.first_name || 'there'}! 👋 I'm Mike Czech, your podcast setup guide. I'm here to help you get your show set up. Click "Need Help?" anytime you have questions!`
        : `Hi ${user?.first_name || 'there'}! 👋 I'm Mike Czech (but you can call me Mike), your podcast assistant.\n\nI can help with:\n• Uploading & editing episodes\n• Publishing & scheduling\n• Template creation\n• **Reporting bugs** (just tell me what's broken!)\n\nWhat can I help you with today?`;

      setMessages([{
        role: 'assistant',
        content: introMessage,
        suggestions: onboardingMode
          ? ["What's this step about?", "Can I skip steps?", "How long does this take?"]
          : ['Show me how to upload audio', 'Where are my episodes?', 'Help me create a template'],
        timestamp: new Date(),
      }]);
    }
  }, [isOpen, user, onboardingMode]);

  // Focus input when chat opens
  useEffect(() => {
    if (isOpen && !isMinimized) {
      inputRef.current?.focus();
    }
  }, [isOpen, isMinimized, messages]);

  // Proactive help for onboarding steps - SHOWS SPEECH BUBBLE ONLY (no auto-open)
  useEffect(() => {
    if (!onboardingMode || !currentStep || !token || !user) return;

    // Don't show proactive help for the same step twice
    if (lastProactiveStep.current === currentStep) return;

    // Show proactive help speech bubble after 15 seconds on this step (increased from 10s)
    const timer = setTimeout(async () => {
      lastProactiveStep.current = currentStep;

      try {
        // Request proactive help from backend
        const response = await makeApi(token).post('/api/assistant/onboarding-help', {
          step: currentStep,
          data: currentStepData,
        });

        if (response.message) {
          // Store the proactive help message to show in speech bubble
          // User must click "Help me!" button or Mike to see it
          setProactiveHelp(response.message);
          // DO NOT auto-open: setIsOpen(true); 
        }
      } catch (error) {
        console.error('Failed to get onboarding help:', error);
      }
    }, 15000); // 15 seconds (less aggressive)

    return () => clearTimeout(timer);
  }, [onboardingMode, currentStep, currentStepData, token, user]);

  // Listen for manual "Need Help?" button clicks
  useEffect(() => {
    const handleOpenAssistant = () => {
      handleOpenMike(); // Use existing open logic (respects desktop/mobile)
      // If in onboarding mode and no messages yet, trigger help immediately
      if (onboardingMode && currentStep && messages.length === 0) {
        (async () => {
          try {
            const response = await makeApi(token).post('/api/assistant/onboarding-help', {
              step: currentStep,
              data: currentStepData,
            });

            if (response.message) {
              setMessages(prev => [...prev, {
                role: 'assistant',
                content: response.message,
                suggestions: response.suggestions,
                timestamp: new Date(),
              }]);
            }
          } catch (error) {
            console.error('Failed to get onboarding help:', error);
          }
        })();
      }
    };

    window.addEventListener('ppp:open-ai-assistant', handleOpenAssistant);
    return () => window.removeEventListener('ppp:open-ai-assistant', handleOpenAssistant);
  }, [onboardingMode, currentStep, currentStepData, token, user, messages.length]);

  // Monitor for user being stuck
  useEffect(() => {
    // Track page actions (you'd call this from other components)
    window.addEventListener('ppp:action-attempted', handleActionAttempted);
    window.addEventListener('ppp:error-occurred', handleErrorOccurred);

    return () => {
      window.removeEventListener('ppp:action-attempted', handleActionAttempted);
      window.removeEventListener('ppp:error-occurred', handleErrorOccurred);
    };
  }, []);

  const handleActionAttempted = (e) => {
    actionsAttempted.current.push(e.detail);
  };

  const handleErrorOccurred = (e) => {
    errorsEncountered.current.push(e.detail);
  };

  const loadGuidanceStatus = async () => {
    try {
      const response = await makeApi(token).get('/api/assistant/guidance/status');
      setGuidanceStatus(response);
    } catch (error) {
      console.error('Failed to load guidance status:', error);
    }
  };

  const checkProactiveHelp = async () => {
    try {
      const timeOnPage = Math.floor((Date.now() - pageStartTime.current) / 1000);
      const response = await makeApi(token).post('/api/assistant/proactive-help', {
        page: window.location.pathname,
        time_on_page: timeOnPage,
        actions_attempted: actionsAttempted.current,
        errors_seen: errorsEncountered.current,
      });

      if (response.needs_help && response.message) {
        setProactiveHelp(response.message);
      }
    } catch (error) {
      console.error('Failed to check proactive help:', error);
    }
  };

  const trackMilestone = async (milestone) => {
    try {
      await makeApi(token).post('/api/assistant/guidance/track', { milestone });
      loadGuidanceStatus();
    } catch (error) {
      console.error('Failed to track milestone:', error);
    }
  };

  // Open Mike in a separate popup window (desktop only)
  const openMikePopup = () => {
    // Check if popup is already open
    if (popupWindow && !popupWindow.closed) {
      popupWindow.focus();
      return;
    }

    // Open new popup window (#2 - alwaysOnTop implemented via focused window management)
    const width = 600;
    const height = 700;
    const left = Math.max(0, (window.screen.width - width) / 2);
    const top = Math.max(0, (window.screen.height - height) / 2);

    const popup = window.open(
      '/mike',
      'MikeCzech',
      `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=no,status=no,toolbar=no,menubar=no,location=no,alwaysRaised=yes`
    );

    if (popup) {
      setPopupWindow(popup);

      // Listen for popup ready message
      const handlePopupReady = (event) => {
        if (event.origin !== window.location.origin) return;
        if (event.data?.type === 'mike-popup-ready' && popup && !popup.closed) {
          // Send initialization data to popup
          popup.postMessage({
            type: 'mike-popup-init',
            token,
            user,
          }, window.location.origin);
        }
      };

      window.addEventListener('message', handlePopupReady);

      // (#2) Keep popup on top by periodically checking if main window is focused
      // When main window gets focus, re-focus the popup to keep Mike visible
      const keepOnTopInterval = setInterval(() => {
        if (popup.closed) {
          clearInterval(keepOnTopInterval);
          return;
        }
        // If main window is focused and popup exists, bring popup to front
        if (document.hasFocus() && popup && !popup.closed) {
          try {
            popup.focus();
          } catch (e) {
            // Silently fail if popup is being closed
          }
        }
      }, 1000); // Check every second

      // Clean up when popup closes
      const checkClosed = setInterval(() => {
        if (popup.closed) {
          clearInterval(checkClosed);
          clearInterval(keepOnTopInterval);
          setPopupWindow(null);
          window.removeEventListener('message', handlePopupReady);
        }
      }, 500);
    } else {
      // Popup blocked - show toast or fallback to inline
      console.warn('Popup blocked - falling back to inline Mike');
      setIsOpen(true);
    }
  };

  // Handle opening Mike (popup on desktop, inline on mobile)
  const handleOpenMike = () => {
    if (isDesktop) {
      openMikePopup();
    } else {
      setIsOpen(true);
    }
  };

  // Parse message content for navigation links: [Link Text](NAVIGATE:/path)
  const parseMessageContent = (content) => {
    if (!content) return content;

    // Pattern: [Link Text](NAVIGATE:/path)
    const navigatePattern = /\[([^\]]+)\]\(NAVIGATE:([^)]+)\)/g;
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = navigatePattern.exec(content)) !== null) {
      // Add text before the match
      if (match.index > lastIndex) {
        parts.push({
          type: 'text',
          content: content.substring(lastIndex, match.index)
        });
      }

      // Add the navigation link
      parts.push({
        type: 'navigate',
        text: match[1],
        path: match[2]
      });

      lastIndex = match.index + match[0].length;
    }

    // Add remaining text
    if (lastIndex < content.length) {
      parts.push({
        type: 'text',
        content: content.substring(lastIndex)
      });
    }

    return parts.length > 0 ? parts : [{ type: 'text', content }];
  };

  // Handle navigation link clicks (ensure they work even if Mike is popped out)
  const handleNavigateClick = (path) => {
    // If popped out, navigate in the opener window and bring it to focus
    if (isPoppedOut && window.opener && !window.opener.closed) {
      // Post message to opener to navigate
      window.opener.postMessage({ type: 'navigate', path }, window.location.origin);
      window.opener.focus();
    } else {
      // Regular window navigation using React Router
      navigate(path);
    }
  };

  const sendMessage = async (messageText) => {
    if (!messageText.trim() || isLoading) return;

    // Add user message
    const userMessage = {
      role: 'user',
      content: messageText,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      // Capture technical context for bug reports (non-blocking)
      let technicalContext = null;
      try {
        technicalContext = captureBugContext();
      } catch (e) {
        console.warn('Failed to capture bug context:', e);
      }

      // Gather context
      const context = {
        page: onboardingMode ? '/onboarding' : window.location.pathname,
        action: actionsAttempted.current[actionsAttempted.current.length - 1],
        error: errorsEncountered.current[errorsEncountered.current.length - 1],
        is_first_time: guidanceStatus?.is_new_user,
        // Onboarding-specific context
        onboarding_mode: onboardingMode,
        onboarding_step: currentStep,
        onboarding_data: currentStepData,
        // Technical context for bug reports
        ...(technicalContext || {}),
      };

      // Send to AI
      const response = await makeApi(token).post('/api/assistant/chat', {
        message: messageText,
        session_id: sessionId,
        context,
      });

      // Add assistant response
      const assistantMessage = {
        role: 'assistant',
        content: response.response,
        suggestions: response.suggestions,
        generatedImage: response.generated_image,  // Include generated image if present
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, assistantMessage]);

      // Handle visual highlighting if provided
      if (response.highlight) {
        applyHighlight(response.highlight, response.highlight_message);
      }

    } catch (error) {
      console.error('Failed to send message:', error);
      console.error('Error details:', {
        message: error?.message,
        status: error?.status,
        detail: error?.detail,
        response: error?.response,
      });

      // Build more helpful error message based on error type
      let errorMessage = `Hey, I'm having trouble connecting to my AI brain right now. 🤔\n\nSomething went wrong on my end. Please try:\n1. Refreshing the page\n2. Asking your question again in a moment\n\nIf this keeps happening, please use the bug report tool to let us know!\n\nSorry about that! - Mike`;

      // Add specific error details if available
      if (error?.status === 503) {
        errorMessage += `\n\n⚠️ Technical detail: AI service unavailable (503)`;
      } else if (error?.status === 401) {
        errorMessage += `\n\n⚠️ Technical detail: Session expired - please refresh the page`;
      } else if (error?.detail) {
        errorMessage += `\n\n⚠️ Technical detail: ${error.detail}`;
      }

      setMessages(prev => [...prev, {
        role: 'assistant',
        content: errorMessage,
        timestamp: new Date(),
        isError: true,
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSuggestionClick = (suggestion) => {
    sendMessage(suggestion);
  };

  const acceptProactiveHelp = () => {
    if (proactiveHelp) {
      setIsOpen(true);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: proactiveHelp,
        timestamp: new Date(),
      }]);
      setProactiveHelp(null);
    }
  };

  const dismissProactiveHelp = () => {
    // Track dismissal time and increase interval by 25% for next reminder (#1)
    lastDismissTime.current = Date.now();
    currentReminderInterval.current = Math.floor(currentReminderInterval.current * 1.25);
    console.log(`Mike reminder dismissed. Next reminder in ${Math.floor(currentReminderInterval.current / 1000)}s`);
    setProactiveHelp(null);
  };

  const handleShowTooltipsAgain = () => {
    // Check if we have a tooltip restart handler for the current page
    if (onRestartTooltips && typeof onRestartTooltips === 'function') {
      onRestartTooltips();
      dismissProactiveHelp(); // Close the proactive help bubble
    }
  };

  // Check if the current page supports tooltips
  const hasTooltipsSupport = currentPage && onRestartTooltips && typeof onRestartTooltips === 'function';

  const applyHighlight = (selector, message) => {
    try {
      // Find the element to highlight
      const element = document.querySelector(selector);
      if (!element) {
        console.warn(`Highlight element not found: ${selector}`);
        return;
      }

      // Remove any existing highlights
      document.querySelectorAll('.ai-highlight-pulse').forEach(el => {
        el.classList.remove('ai-highlight-pulse');
      });

      // Scroll element into view
      element.scrollIntoView({ behavior: 'smooth', block: 'center' });

      // Add highlight class
      element.classList.add('ai-highlight-pulse');

      // Create and show tooltip if message provided
      if (message) {
        showHighlightTooltip(element, message);
      }

      // Remove highlight after 10 seconds
      setTimeout(() => {
        element.classList.remove('ai-highlight-pulse');
        removeHighlightTooltip();
      }, 10000);

    } catch (error) {
      console.error('Failed to apply highlight:', error);
    }
  };

  const showHighlightTooltip = (element, message) => {
    // Remove any existing tooltip
    removeHighlightTooltip();

    // Create tooltip element
    const tooltip = document.createElement('div');
    tooltip.id = 'ai-highlight-tooltip';
    tooltip.className = 'fixed z-[9999] bg-blue-600 text-white px-4 py-2 rounded-lg shadow-xl text-sm max-w-xs pointer-events-none';
    tooltip.textContent = message;

    // Position tooltip near element
    const rect = element.getBoundingClientRect();
    tooltip.style.top = `${rect.top - 50}px`;
    tooltip.style.left = `${rect.left + rect.width / 2}px`;
    tooltip.style.transform = 'translateX(-50%)';

    // Add arrow pointing down
    const arrow = document.createElement('div');
    arrow.className = 'absolute bottom-[-6px] left-1/2 -translate-x-1/2 w-0 h-0 border-l-[6px] border-l-transparent border-r-[6px] border-r-transparent border-t-[6px] border-t-blue-600';
    tooltip.appendChild(arrow);

    document.body.appendChild(tooltip);
  };

  const removeHighlightTooltip = () => {
    const tooltip = document.getElementById('ai-highlight-tooltip');
    if (tooltip) {
      tooltip.remove();
    }
  };

  if (!token || !user) return null;

  return (
    <>
      {/* Proactive Help Notification (mobile only - desktop uses speech bubble) */}
      {proactiveHelp && !isOpen && !isDesktop && (
        <div className="fixed bottom-24 right-6 max-w-sm bg-white border-2 border-blue-500 rounded-lg shadow-lg p-4 z-50 animate-bounce">
          <div className="flex items-start gap-3">
            <HelpCircle className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm text-gray-800">{proactiveHelp}</p>
              <div className="flex flex-col gap-2 mt-3">
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => { handleOpenMike(); acceptProactiveHelp(); }}>
                    Yes, help me!
                  </Button>
                  <Button size="sm" variant="ghost" onClick={dismissProactiveHelp}>
                    Dismiss
                  </Button>
                </div>
                {hasTooltipsSupport && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleShowTooltipsAgain}
                    className="w-full"
                  >
                    Show tooltips again
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Chat Widget - Responsive sizing to avoid covering content (mobile only, desktop uses popup) */}
      {isOpen && !isDesktop ? (
        <div className={`fixed bg-white border border-gray-300 shadow-2xl flex flex-col
          ${isPoppedOut
            ? 'top-[10%] left-[10%] w-[600px] h-[700px] z-[70]'
            : onboardingMode
              ? 'bottom-6 right-6 z-[60]' // Higher z-index for onboarding, positioned right
              : 'bottom-6 right-6 z-50'
          }
          ${isMinimized
            ? 'w-80 h-14'
            : isPoppedOut
              ? ''
              : 'inset-4 md:inset-auto md:bottom-6 md:right-6 md:w-96 md:h-[500px] md:max-h-[min(500px,calc(100vh-10rem))] md:rounded-lg'
          }
          rounded-lg`}
          style={isPoppedOut ? { resize: 'both', overflow: 'hidden', minWidth: '400px', minHeight: '500px', maxWidth: '90vw', maxHeight: '90vh' } : {}}
        >

          {/* Header */}
          <div className="flex items-center justify-between p-3 md:p-4 border-b bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-t-lg flex-shrink-0 safe-top">
            <div className="flex items-center gap-2">
              <MessageCircle className="w-4 h-4 md:w-5 md:h-5" />
              <span className="font-semibold text-sm md:text-base">Mike Czech</span>
              {isLoading && (
                <span className="text-xs bg-white/20 px-2 py-0.5 rounded-full">Thinking...</span>
              )}
            </div>
            <div className="flex items-center gap-1 md:gap-2">
              {/* Bug Report Button */}
              <button
                onClick={() => {
                  setInputValue("I found a bug: ");
                  setTimeout(() => inputRef.current?.focus(), 100);
                }}
                className="text-xs bg-red-500 hover:bg-red-600 text-white px-2 py-1 rounded-full flex items-center gap-1 transition-colors touch-target-icon"
                title="Report a bug to the development team"
              >
                <AlertCircle className="w-3 h-3" />
                <span className="hidden md:inline">Report Bug</span>
              </button>
              {/* Feature Request Button */}
              <button
                onClick={() => {
                  setInputValue("I have a feature request: ");
                  setTimeout(() => inputRef.current?.focus(), 100);
                }}
                className="text-xs bg-green-500 hover:bg-green-600 text-white px-2 py-1 rounded-full flex items-center gap-1 transition-colors touch-target-icon"
                title="Request a new feature"
              >
                <Lightbulb className="w-3 h-3" />
                <span className="hidden md:inline">Request Feature</span>
              </button>
              <button
                onClick={() => setIsPoppedOut(!isPoppedOut)}
                className="hover:bg-white/20 p-1 rounded transition-colors hidden md:block"
                title={isPoppedOut ? "Dock to corner" : "Pop out & resize"}
              >
                <Maximize2 className="w-4 h-4" />
              </button>
              <button
                onClick={() => setIsMinimized(!isMinimized)}
                className="hover:bg-white/20 p-1 rounded transition-colors hidden md:block"
                title={isMinimized ? "Expand" : "Minimize"}
              >
                {isMinimized ? <Maximize2 className="w-4 h-4" /> : <Minimize2 className="w-4 h-4" />}
              </button>
              <button
                onClick={() => {
                  setIsOpen(false);
                  setIsPoppedOut(false);
                }}
                className="hover:bg-white/20 p-1.5 md:p-1 rounded transition-colors touch-target-icon"
                title="Close"
              >
                <X className="w-5 h-5 md:w-4 md:h-4" />
              </button>
            </div>
          </div>

          {!isMinimized && (
            <>
              {/* Messages */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
                {messages.map((msg, idx) => (
                  <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[85%] rounded-lg px-4 py-2 ${msg.role === 'user'
                        ? 'bg-blue-600 text-white'
                        : msg.isError
                          ? 'bg-red-100 text-red-800 border border-red-300'
                          : 'bg-white border border-gray-200 text-gray-800'
                      }`}>
                      {/* Parse and render content with navigation links */}
                      <div className="text-sm whitespace-pre-wrap">
                        {parseMessageContent(msg.content).map((part, partIdx) => {
                          if (part.type === 'navigate') {
                            return (
                              <button
                                key={partIdx}
                                onClick={() => handleNavigateClick(part.path)}
                                className={`inline underline font-medium hover:opacity-80 transition-opacity ${msg.role === 'user' ? 'text-white' : 'text-blue-600'
                                  }`}
                              >
                                {part.text}
                              </button>
                            );
                          }
                          return <span key={partIdx}>{part.content}</span>;
                        })}
                      </div>

                      {/* Generated podcast cover image */}
                      {msg.generatedImage && (
                        <div className="mt-3 space-y-2">
                          <img
                            src={msg.generatedImage}
                            alt="Generated podcast cover"
                            className="w-full rounded-lg border-2 border-purple-300 shadow-md"
                          />
                          <div className="grid grid-cols-3 gap-2">
                            <button
                              onClick={async () => {
                                try {
                                  // Convert base64 to File object
                                  const response = await fetch(msg.generatedImage);
                                  const blob = await response.blob();
                                  const file = new File([blob], 'podcast-cover.png', { type: 'image/png' });

                                  // Dispatch custom event with the generated image file
                                  const event = new CustomEvent('ai-generated-cover', { detail: { file } });
                                  window.dispatchEvent(event);

                                  // Visual feedback
                                  setMessages(prev => [...prev, {
                                    role: 'assistant',
                                    content: '✅ Cover image sent to your form! Check the cover art upload section.',
                                    timestamp: new Date(),
                                  }]);
                                } catch (error) {
                                  console.error('Failed to use generated image:', error);
                                  setMessages(prev => [...prev, {
                                    role: 'assistant',
                                    content: '❌ Failed to use the image. Try downloading it instead.',
                                    timestamp: new Date(),
                                    isError: true,
                                  }]);
                                }
                              }}
                              className="text-xs bg-green-600 hover:bg-green-700 text-white px-3 py-2 rounded transition-colors"
                            >
                              ✨ Use This
                            </button>
                            <a
                              href={msg.generatedImage}
                              download="podcast-cover.png"
                              className="text-xs bg-purple-600 hover:bg-purple-700 text-white px-3 py-2 rounded text-center transition-colors"
                            >
                              📥 Download
                            </a>
                            <button
                              onClick={() => handleSuggestionClick("Generate another variation")}
                              className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-800 px-3 py-2 rounded transition-colors"
                            >
                              🔄 Retry
                            </button>
                          </div>
                        </div>
                      )}

                      <span className="text-xs opacity-60 mt-1 block">
                        {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                  </div>
                ))}
                {isLoading && (
                  <div className="flex justify-start">
                    <div className="bg-white border border-gray-200 rounded-lg px-4 py-2">
                      <div className="flex gap-1">
                        <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                        <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                        <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                      </div>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Input */}
              <div className="p-3 md:p-4 border-t bg-white rounded-b-lg flex-shrink-0 safe-bottom">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (inputValue.trim() && !isLoading) {
                      sendMessage(inputValue);
                      // Keep focus on input after sending
                      setTimeout(() => inputRef.current?.focus(), 0);
                    }
                  }}
                  className="flex gap-2"
                >
                  <input
                    ref={inputRef}
                    type="text"
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    placeholder="Ask me anything..."
                    className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm md:text-base focus:outline-none focus:ring-2 focus:ring-blue-500"
                    disabled={isLoading}
                    autoFocus
                  />
                  <Button
                    type="submit"
                    size="sm"
                    disabled={!inputValue.trim() || isLoading}
                    className="bg-blue-600 hover:bg-blue-700 touch-target"
                  >
                    <Send className="w-4 h-4" />
                  </Button>
                </form>

                {/* Improved bug reporting hint with better visibility */}
                <div className="flex items-center gap-2 mt-2 text-xs bg-blue-50 border border-blue-200 rounded-md px-2 py-1">
                  <AlertCircle className="w-3.5 h-3.5 text-blue-600" />
                  <span className="hidden md:inline text-blue-800 font-medium">
                    💡 Tip: Found a bug? Just tell me and I'll report it to the dev team!
                  </span>
                  <span className="md:hidden text-blue-800 font-medium">
                    💡 Bug? Tell me!
                  </span>
                </div>
              </div>
            </>
          )}
        </div>
      ) : (
        /* AI Assistant Character (Clippy-style) - HIDDEN when popped out (#3) */
        !popupWindow && ( // Only show if popup is NOT open
          <div className={`fixed z-50 safe-bottom safe-right transition-all duration-300
            bottom-4 right-4 
            lg:left-2 lg:right-auto lg:bottom-[70px]
          `}>
            {/* Speech Bubble - Shows when proactive help is available (desktop only) */}
            {proactiveHelp && (
              <div className={`hidden md:block absolute mb-2 animate-bounce-gentle
              lg:left-16 lg:bottom-4 lg:mb-0 lg:ml-2 w-64
            `}>
                <div className="relative bg-white border-2 border-purple-400 rounded-2xl shadow-xl p-4">
                  {/* Speech bubble tail - adjusted for right side placement relative to assistant */}
                  <div className="absolute top-[20px] -left-[10px] w-0 h-0 border-t-[10px] border-t-transparent border-b-[10px] border-b-transparent border-r-[10px] border-r-purple-400"></div>
                  <div className="absolute top-[22px] -left-[7px] w-0 h-0 border-t-[8px] border-t-transparent border-b-[8px] border-b-transparent border-r-[8px] border-r-white"></div>

                  {/* Message content */}
                  <p className="text-sm text-gray-800 mb-3">{proactiveHelp}</p>
                  <div className="flex flex-col gap-2">
                    <div className="flex gap-2 justify-center">
                      <button
                        onClick={() => {
                          handleOpenMike(); // Open chat interface (popup on desktop, inline on mobile)
                          acceptProactiveHelp(); // Add message to chat
                        }}
                        className="px-3 py-1 bg-purple-600 text-white text-xs rounded-full hover:bg-purple-700 transition-colors touch-target flex items-center justify-center"
                      >
                        Help me!
                      </button>
                      <button
                        onClick={dismissProactiveHelp}
                        className="px-3 py-1 bg-gray-200 text-gray-700 text-xs rounded-full hover:bg-gray-300 transition-colors touch-target flex items-center justify-center"
                      >
                        Dismiss
                      </button>
                    </div>
                    {hasTooltipsSupport && (
                      <button
                        onClick={handleShowTooltipsAgain}
                        className="px-3 py-1 bg-blue-50 text-blue-700 text-xs rounded-full hover:bg-blue-100 transition-colors touch-target border border-blue-200 flex items-center justify-center"
                      >
                        Show tooltips again
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* AI Character - Mobile: FAB with icon, Desktop: Mike Czech mascot */}
            <button
              onClick={handleOpenMike}
              className={`relative touch-target transition-all hover:scale-110 focus:outline-none focus:ring-4 focus:ring-purple-400 rounded-full flex items-center justify-center md:block overflow-hidden
              bg-purple-600 shadow-xl w-14 h-14 
              md:bg-transparent md:shadow-none md:w-20 md:h-20
            `}
              title="Click me for help! I'm Mike Czech!"
            >
              {/* Mobile: MessageCircle icon */}
              <MessageCircle className="w-6 h-6 text-white md:hidden" />

              {/* Desktop: Mike Czech Image */}
              <img
                src="/MikeCzech.png"
                alt="Mike Czech - Your AI Assistant"
                className="hidden md:block w-full h-full object-contain drop-shadow-lg"
              />

              {/* Notification badge for new users */}
              {guidanceStatus?.is_new_user && (
                <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 rounded-full animate-pulse border-2 border-white flex items-center justify-center text-white text-xs font-bold">!</span>
              )}
            </button>
          </div>
        ) /* Close the !popupWindow conditional */
      )}
    </>
  );
}
