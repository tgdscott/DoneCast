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

export default function AIAssistant({ token, user }) {
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
  
  // Show welcome message for new users
  useEffect(() => {
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
  }, [guidanceStatus, user]);
  
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
        page: window.location.pathname,
        action: actionsAttempted.current[actionsAttempted.current.length - 1],
        error: errorsEncountered.current[errorsEncountered.current.length - 1],
        is_first_time: guidanceStatus?.is_new_user,
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
      console.error('Error details:', error.response?.data || error.message);
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
      
      {/* Chat Widget */}
      {isOpen ? (
        <div className={`fixed bottom-6 right-6 bg-white border border-gray-300 rounded-lg shadow-2xl z-50 flex flex-col
          ${isMinimized ? 'w-80 h-14' : 'w-96 h-[600px]'}`}>
          
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-t-lg">
            <div className="flex items-center gap-2">
              <MessageCircle className="w-5 h-5" />
              <span className="font-semibold">AI Assistant</span>
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
        /* Floating Button */
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 w-14 h-14 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-full shadow-lg hover:shadow-xl transition-all hover:scale-110 z-50 flex items-center justify-center"
        >
          <MessageCircle className="w-6 h-6" />
          {guidanceStatus?.is_new_user && (
            <span className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 rounded-full animate-pulse"></span>
          )}
        </button>
      )}
    </>
  );
}
