/**
 * AI Assistant Standalone Popup Window
 * 
 * This renders Mike Czech in a separate browser window for desktop users.
 * Communicates with the main window via postMessage API.
 */

import { useState, useEffect, useRef } from 'react';
import { MessageCircle, X, Send, AlertCircle, Lightbulb } from 'lucide-react';
import { Button } from '../ui/button';
import { makeApi } from '../../lib/apiClient';

export default function AIAssistantPopup() {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId] = useState(() => `session_${Date.now()}_${Math.random()}`);
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const hasShownIntro = useRef(false);
  
  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);
  
  // Initialize from opener window
  useEffect(() => {
    if (window.opener && !window.opener.closed) {
      // Request initialization data from opener
      window.opener.postMessage({ type: 'mike-popup-ready' }, window.location.origin);
      
      // Listen for initialization data
      const handleMessage = (event) => {
        if (event.origin !== window.location.origin) return;
        
        const { type, token: openerToken, user: openerUser } = event.data;
        
        if (type === 'mike-popup-init') {
          setToken(openerToken);
          setUser(openerUser);
        } else if (type === 'navigate') {
          // Ignore navigate messages in popup (those are for main window)
        }
      };
      
      window.addEventListener('message', handleMessage);
      return () => window.removeEventListener('message', handleMessage);
    } else {
      // No opener window, show error
      setMessages([{
        role: 'assistant',
        content: "⚠️ I can't connect to the main window. Please reopen me from the main application.",
        timestamp: new Date(),
        isError: true,
      }]);
    }
  }, []);
  
  // Show welcome message when initialized
  useEffect(() => {
    if (token && user && !hasShownIntro.current) {
      hasShownIntro.current = true;
      
      const introMessage = `Hi ${user?.first_name || 'there'}! 👋 I'm Mike Czech (but you can call me Mike), your podcast assistant.\n\nI can help with:\n• Uploading & editing episodes\n• Publishing & scheduling\n• Template creation\n• **Reporting bugs** (just tell me what's broken!)\n\nWhat can I help you with today?`;
      
      setMessages([{
        role: 'assistant',
        content: introMessage,
        timestamp: new Date(),
      }]);
      
      // Focus input after intro
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [token, user]);
  
  // Parse message content for navigation links: [Link Text](NAVIGATE:/path)
  const parseMessageContent = (content) => {
    if (!content) return content;
    
    const navigatePattern = /\[([^\]]+)\]\(NAVIGATE:([^)]+)\)/g;
    const parts = [];
    let lastIndex = 0;
    let match;
    
    while ((match = navigatePattern.exec(content)) !== null) {
      if (match.index > lastIndex) {
        parts.push({
          type: 'text',
          content: content.substring(lastIndex, match.index)
        });
      }
      
      parts.push({
        type: 'navigate',
        text: match[1],
        path: match[2]
      });
      
      lastIndex = match.index + match[0].length;
    }
    
    if (lastIndex < content.length) {
      parts.push({
        type: 'text',
        content: content.substring(lastIndex)
      });
    }
    
    return parts.length > 0 ? parts : [{ type: 'text', content }];
  };
  
  // Handle navigation link clicks - send to opener window
  const handleNavigateClick = (path) => {
    if (window.opener && !window.opener.closed) {
      window.opener.postMessage({ type: 'navigate', path }, window.location.origin);
      window.opener.focus();
    } else {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: '⚠️ Main window is closed. Please reopen the application to navigate.',
        timestamp: new Date(),
        isError: true,
      }]);
    }
  };
  
  const sendMessage = async (messageText) => {
    if (!messageText.trim() || isLoading || !token) return;
    
    const userMessage = {
      role: 'user',
      content: messageText,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);
    
    try {
      const context = {
        page: window.opener ? 'popup' : 'unknown',
        is_popup: true,
      };
      
      const response = await makeApi(token).post('/api/assistant/chat', {
        message: messageText,
        session_id: sessionId,
        context,
      });
      
      const assistantMessage = {
        role: 'assistant',
        content: response.response,
        generatedImage: response.generated_image,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, assistantMessage]);
      
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
  
  if (!token || !user) {
    return (
      <div className="flex items-center justify-center h-screen bg-gradient-to-br from-purple-50 to-blue-50">
        <div className="text-center">
          <MessageCircle className="w-16 h-16 text-purple-600 mx-auto mb-4 animate-bounce" />
          <h2 className="text-xl font-semibold text-gray-800 mb-2">Connecting to Mike Czech...</h2>
          <p className="text-sm text-gray-600">Initializing AI Assistant</p>
        </div>
      </div>
    );
  }
  
  return (
    <div className="flex flex-col h-screen bg-gradient-to-br from-purple-50 to-blue-50">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-lg flex-shrink-0">
        <div className="flex items-center gap-3">
          <img 
            src="/MikeCzech.png" 
            alt="Mike Czech"
            className="w-10 h-10 rounded-full border-2 border-white shadow-md"
          />
          <div>
            <span className="font-semibold text-lg">Mike Czech</span>
            <p className="text-xs text-white/80">Your AI Podcast Assistant</p>
          </div>
          {isLoading && (
            <span className="text-xs bg-white/20 px-2 py-0.5 rounded-full animate-pulse">Thinking...</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Bug Report Button */}
          <button
            onClick={() => {
              setInputValue("I found a bug: ");
              setTimeout(() => inputRef.current?.focus(), 100);
            }}
            className="text-xs bg-red-500 hover:bg-red-600 text-white px-2 py-1 rounded-full flex items-center gap-1 transition-colors"
            title="Report a bug to the development team"
          >
            <AlertCircle className="w-3 h-3" />
            <span>Report Bug</span>
          </button>
          {/* Feature Request Button */}
          <button
            onClick={() => {
              setInputValue("I have a feature request: ");
              setTimeout(() => inputRef.current?.focus(), 100);
            }}
            className="text-xs bg-green-500 hover:bg-green-600 text-white px-2 py-1 rounded-full flex items-center gap-1 transition-colors"
            title="Request a new feature"
          >
            <Lightbulb className="w-3 h-3" />
            <span>Request Feature</span>
          </button>
          <button
            onClick={() => window.close()}
            className="hover:bg-white/20 p-2 rounded transition-colors"
            title="Close Mike"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>
      
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[80%] rounded-lg px-4 py-3 shadow-md ${
              msg.role === 'user'
                ? 'bg-blue-600 text-white'
                : msg.isError
                ? 'bg-red-100 text-red-800 border border-red-300'
                : 'bg-white border border-gray-200 text-gray-800'
            }`}>
              <div className="text-sm whitespace-pre-wrap">
                {parseMessageContent(msg.content).map((part, partIdx) => {
                  if (part.type === 'navigate') {
                    return (
                      <button
                        key={partIdx}
                        onClick={() => handleNavigateClick(part.path)}
                        className={`inline underline font-medium hover:opacity-80 transition-opacity ${
                          msg.role === 'user' ? 'text-white' : 'text-blue-600'
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
                          const response = await fetch(msg.generatedImage);
                          const blob = await response.blob();
                          const file = new File([blob], 'podcast-cover.png', { type: 'image/png' });
                          
                          if (window.opener && !window.opener.closed) {
                            // Send to opener window
                            const event = new CustomEvent('ai-generated-cover', { detail: { file } });
                            window.opener.dispatchEvent(event);
                            
                            setMessages(prev => [...prev, {
                              role: 'assistant',
                              content: '✅ Cover image sent to your main window! Check the cover art upload section.',
                              timestamp: new Date(),
                            }]);
                          } else {
                            throw new Error('Main window not available');
                          }
                        } catch (error) {
                          console.error('Failed to use generated image:', error);
                          setMessages(prev => [...prev, {
                            role: 'assistant',
                            content: '❌ Failed to send to main window. Try downloading it instead.',
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
                      onClick={() => sendMessage("Generate another variation")}
                      className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-800 px-3 py-2 rounded transition-colors"
                    >
                      🔄 Retry
                    </button>
                  </div>
                </div>
              )}
              
              <span className="text-xs opacity-60 mt-2 block">
                {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 shadow-md">
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
      <div className="p-4 border-t bg-white shadow-lg flex-shrink-0">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (inputValue.trim() && !isLoading) {
              sendMessage(inputValue);
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
            className="flex-1 border border-gray-300 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={isLoading}
            autoFocus
          />
          <Button
            type="submit"
            size="lg"
            disabled={!inputValue.trim() || isLoading}
            className="bg-blue-600 hover:bg-blue-700"
          >
            <Send className="w-5 h-5" />
          </Button>
        </form>
        
        {/* Improved bug reporting hint with better visibility */}
        <div className="flex items-center gap-2 mt-2 text-xs bg-blue-50 border border-blue-200 rounded-md px-2 py-1">
          <AlertCircle className="w-3.5 h-3.5 text-blue-600" />
          <span className="text-blue-800 font-medium">
            💡 Tip: Found a bug? Just tell me and I'll report it to the dev team!
          </span>
        </div>
      </div>
    </div>
  );
}
