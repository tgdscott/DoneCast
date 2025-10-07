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
import { MessageCircle, X, Send, Minimize2, Maximize2, HelpCircle, AlertCircle } from 'lucide-react';
import { Button } from '../ui/button';
import { makeApi } from '../../lib/apiClient';

export default function AIAssistant({ token, user, onboardingMode = false, currentStep = null, currentStepData = null }) {
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId] = useState(() => `session_${Date.now()}_${Math.random()}`);
  const [guidanceStatus, setGuidanceStatus] = useState(null);
  const [proactiveHelp, setProactiveHelp] = useState(null);
  
  const messagesEndRef = useRef(null);
  const pageStartTime = useRef(Date.now());
  const actionsAttempted = useRef([]);
  const errorsEncountered = useRef([]);
  const lastProactiveStep = useRef(null);
  
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
  
  // Check for proactive help periodically
  useEffect(() => {
    if (!token || !user || !isOpen) return;
    
    const checkInterval = setInterval(() => {
      checkProactiveHelp();
    }, 60000); // Check every minute
    
    return () => clearInterval(checkInterval);
  }, [token, user, isOpen]);
  
  // Show welcome message for new users (unless in onboarding mode)
  useEffect(() => {
    if (onboardingMode) return; // Skip welcome for onboarding - we'll show proactive help instead
    if (guidanceStatus?.is_new_user && !guidanceStatus?.progress?.has_seen_welcome) {
      setMessages([{
        role: 'assistant',
        content: `Hi ${user?.first_name || 'there'}! 👋 Welcome to Podcast Plus Plus! I'm your AI assistant, here to help you create amazing podcasts.\n\nThis is your first time here - would you like a quick guided tour to get started?`,
        suggestions: ['Yes, show me around!', 'No thanks, I\'ll explore'],
        timestamp: new Date(),
      }]);
      setIsOpen(true);
      trackMilestone('seen_welcome');
    }
  }, [guidanceStatus, user, onboardingMode]);
  
  // Proactive help for onboarding steps
  useEffect(() => {
    if (!onboardingMode || !currentStep || !token || !user) return;
    
    // Don't show proactive help for the same step twice
    if (lastProactiveStep.current === currentStep) return;
    
    // Show proactive help after 10 seconds on this step
    const timer = setTimeout(async () => {
      lastProactiveStep.current = currentStep;
      
      try {
        // Request proactive help from backend
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
          setIsOpen(true); // Auto-open the assistant
        }
      } catch (error) {
        console.error('Failed to get onboarding help:', error);
      }
    }, 10000); // 10 seconds
    
    return () => clearTimeout(timer);
  }, [onboardingMode, currentStep, currentStepData, token, user]);
  
  // Listen for manual "Need Help?" button clicks
  useEffect(() => {
    const handleOpenAssistant = () => {
      setIsOpen(true);
      // If in onboarding mode and no messages yet, trigger help immediately
      if (onboardingMode && currentStep && messages.length === 0) {
        (async () => {
          try {
            const response = await makeApi(token).post('/api/assistant/onboarding-help', {
              step: currentStep,
              data: currentStepData,
            });
            if (response.message) {
              setMessages([{
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
  }, [onboardingMode, currentStep, currentStepData, token, messages.length]);
  
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
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, assistantMessage]);
      
    } catch (error) {
      console.error('Failed to send message:', error);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, I\'m having trouble connecting right now. Please try again in a moment.',
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
    setProactiveHelp(null);
  };
  
  if (!token || !user) return null;
  
  return (
    <>
      {/* Proactive Help Notification */}
      {proactiveHelp && !isOpen && (
        <div className="fixed bottom-24 right-6 max-w-sm bg-white border-2 border-blue-500 rounded-lg shadow-lg p-4 z-50 animate-bounce">
          <div className="flex items-start gap-3">
            <HelpCircle className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm text-gray-800">{proactiveHelp}</p>
              <div className="flex gap-2 mt-3">
                <Button size="sm" onClick={acceptProactiveHelp}>
                  Yes, help me!
                </Button>
                <Button size="sm" variant="ghost" onClick={dismissProactiveHelp}>
                  No thanks
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* Chat Widget - Responsive sizing to avoid covering content */}
      {isOpen ? (
        <div className={`fixed bg-white border border-gray-300 rounded-lg shadow-2xl flex flex-col
          ${onboardingMode 
            ? 'bottom-6 right-6 z-[60]' // Higher z-index for onboarding, positioned right
            : 'bottom-6 right-6 z-50'
          }
          ${isMinimized 
            ? 'w-80 h-14' 
            : 'w-96 max-w-[calc(100vw-3rem)] h-[500px] max-h-[min(500px,calc(100vh-10rem))]'
          }`}>
          
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-t-lg">
            <div className="flex items-center gap-2">
              <MessageCircle className="w-5 h-5" />
              <span className="font-semibold">Mike D. Rop</span>
              {isLoading && (
                <span className="text-xs bg-white/20 px-2 py-0.5 rounded-full">Thinking...</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setIsMinimized(!isMinimized)}
                className="hover:bg-white/20 p-1 rounded transition-colors"
              >
                {isMinimized ? <Maximize2 className="w-4 h-4" /> : <Minimize2 className="w-4 h-4" />}
              </button>
              <button
                onClick={() => setIsOpen(false)}
                className="hover:bg-white/20 p-1 rounded transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
          
          {!isMinimized && (
            <>
              {/* Messages */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
                {messages.map((msg, idx) => (
                  <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[85%] rounded-lg px-4 py-2 ${
                      msg.role === 'user'
                        ? 'bg-blue-600 text-white'
                        : msg.isError
                        ? 'bg-red-100 text-red-800 border border-red-300'
                        : 'bg-white border border-gray-200 text-gray-800'
                    }`}>
                      <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                      
                      {/* Quick action suggestions */}
                      {msg.suggestions && (
                        <div className="flex flex-wrap gap-2 mt-3">
                          {msg.suggestions.map((suggestion, i) => (
                            <button
                              key={i}
                              onClick={() => handleSuggestionClick(suggestion)}
                              className="text-xs bg-blue-100 hover:bg-blue-200 text-blue-800 px-2 py-1 rounded transition-colors"
                            >
                              {suggestion}
                            </button>
                          ))}
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
              <div className="p-4 border-t bg-white rounded-b-lg">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    sendMessage(inputValue);
                  }}
                  className="flex gap-2"
                >
                  <input
                    type="text"
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    placeholder="Ask me anything..."
                    className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    disabled={isLoading}
                  />
                  <Button
                    type="submit"
                    size="sm"
                    disabled={!inputValue.trim() || isLoading}
                    className="bg-blue-600 hover:bg-blue-700"
                  >
                    <Send className="w-4 h-4" />
                  </Button>
                </form>
                
                <div className="flex items-center gap-2 mt-2 text-xs text-gray-500">
                  <AlertCircle className="w-3 h-3" />
                  <span>Found a bug? Just tell me and I'll report it!</span>
                </div>
              </div>
            </>
          )}
        </div>
      ) : (
        /* AI Assistant Character (Clippy-style) */
        <div className="fixed bottom-6 right-6 z-50">
          {/* Speech Bubble - Shows when proactive help is available */}
          {proactiveHelp && (
            <div className="absolute bottom-20 right-0 mb-2 animate-bounce-gentle">
              <div className="relative bg-white border-2 border-purple-400 rounded-2xl shadow-xl p-4 max-w-xs">
                {/* Speech bubble tail */}
                <div className="absolute bottom-[-10px] right-8 w-0 h-0 border-l-[10px] border-l-transparent border-r-[10px] border-r-transparent border-t-[10px] border-t-purple-400"></div>
                <div className="absolute bottom-[-7px] right-[33px] w-0 h-0 border-l-[8px] border-l-transparent border-r-[8px] border-r-transparent border-t-[8px] border-t-white"></div>
                
                {/* Message content */}
                <p className="text-sm text-gray-800 mb-3">{proactiveHelp}</p>
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={acceptProactiveHelp}
                    className="px-3 py-1 bg-purple-600 text-white text-xs rounded-full hover:bg-purple-700 transition-colors"
                  >
                    Help me!
                  </button>
                  <button
                    onClick={dismissProactiveHelp}
                    className="px-3 py-1 bg-gray-200 text-gray-700 text-xs rounded-full hover:bg-gray-300 transition-colors"
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            </div>
          )}
          
          {/* AI Character - Clickable mascot */}
          <button
            onClick={() => setIsOpen(true)}
            className="relative w-24 h-24 transition-all hover:scale-110 focus:outline-none focus:ring-4 focus:ring-purple-400 rounded-full"
            title="Click me for help!"
          >
            {/* Character SVG */}
            <svg viewBox="0 0 200 200" className="w-full h-full drop-shadow-xl">
              {/* Shadow */}
              <ellipse cx="100" cy="180" rx="60" ry="10" fill="#D8D8E8" opacity="0.4"/>
              
              {/* Body */}
              <ellipse cx="100" cy="150" rx="70" ry="35" fill="#8B5CF6"/>
              
              {/* Head */}
              <circle cx="100" cy="100" r="55" fill="url(#gradient-head)"/>
              <defs>
                <linearGradient id="gradient-head" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#A855F7"/>
                  <stop offset="100%" stopColor="#D946EF"/>
                </linearGradient>
              </defs>
              
              {/* Headphones */}
              <path d="M 45 90 Q 40 100 45 110" stroke="#8B5CF6" strokeWidth="8" fill="none" strokeLinecap="round"/>
              <path d="M 155 90 Q 160 100 155 110" stroke="#8B5CF6" strokeWidth="8" fill="none" strokeLinecap="round"/>
              <ellipse cx="40" cy="100" rx="12" ry="18" fill="#C084FC"/>
              <ellipse cx="160" cy="100" rx="12" ry="18" fill="#C084FC"/>
              <path d="M 50 70 Q 100 50 150 70" stroke="#8B5CF6" strokeWidth="10" fill="none" strokeLinecap="round"/>
              
              {/* Eyes */}
              <ellipse cx="80" cy="95" rx="12" ry="16" fill="white"/>
              <ellipse cx="120" cy="95" rx="12" ry="16" fill="white"/>
              <circle cx="80" cy="98" r="7" fill="#2D3748"/>
              <circle cx="120" cy="98" r="7" fill="#2D3748"/>
              <circle cx="82" cy="96" r="3" fill="white"/> {/* Eye shine */}
              <circle cx="122" cy="96" r="3" fill="white"/>
              
              {/* Eyebrows */}
              <path d="M 68 80 Q 80 75 90 78" stroke="#8B5CF6" strokeWidth="3" fill="none" strokeLinecap="round"/>
              <path d="M 110 78 Q 120 75 132 80" stroke="#8B5CF6" strokeWidth="3" fill="none" strokeLinecap="round"/>
              
              {/* Happy smile */}
              <path d="M 75 115 Q 100 125 125 115" stroke="#8B5CF6" strokeWidth="3" fill="none" strokeLinecap="round"/>
              
              {/* Idea lightbulb */}
              <circle cx="50" cy="40" r="12" fill="#FFA726" opacity="0.9"/>
              <path d="M 48 52 L 48 56 L 52 56 L 52 52 Z" fill="#9C27B0"/>
              <path d="M 45 38 L 43 35" stroke="#FFA726" strokeWidth="2" strokeLinecap="round"/>
              <path d="M 55 38 L 57 35" stroke="#FFA726" strokeWidth="2" strokeLinecap="round"/>
              <path d="M 50 30 L 50 27" stroke="#FFA726" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            
            {/* Notification badge for new users */}
            {guidanceStatus?.is_new_user && (
              <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 rounded-full animate-pulse border-2 border-white flex items-center justify-center text-white text-xs font-bold">!</span>
            )}
          </button>
        </div>
      )}
    </>
  );
}
