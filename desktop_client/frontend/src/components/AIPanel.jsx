import { useState, useRef, useEffect } from 'react';
import { X, Bot, Send, User, Loader2 } from 'lucide-react';
import { getApiBase, getApiKey } from '../services/api';

const EXAMPLE_QUERIES = [
  "Show flagged vehicles in the last hour",
  "How many alerts were triggered today?",
  "Which camera has the most detections?",
  "List all stolen plate matches",
];

export default function AIPanel({ onClose }) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: "Hello! I'm your AI surveillance assistant. Ask me about recent alerts, detections, or camera activity. For example:\n\n• \"Show flagged vehicles in the last hour\"\n• \"Which camera has the most detections?\"\n• \"List all stolen plate matches\"",
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isOnline, setIsOnline] = useState(true);
  const [isChecking, setIsChecking] = useState(true);
  
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const checkStatus = async () => {
    setIsChecking(true);
    try {
      const res = await fetch(`${getApiBase()}/ai/status`, {
        headers: { 'X-API-Key': getApiKey() || '' }
      });
      if (res.ok) {
        const data = await res.json();
        setIsOnline(data.status === 'online');
      } else {
        setIsOnline(false);
      }
    } catch {
      setIsOnline(false);
    } finally {
      setIsChecking(false);
    }
  };

  useEffect(() => {
    checkStatus();
  }, []);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    const userMessage = { role: 'user', content: trimmed };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const res = await fetch(`${getApiBase()}/ai/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': getApiKey() || '',
        },
        body: JSON.stringify({ query: trimmed }),
      });

      if (res.ok) {
        const data = await res.json();
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: data.response || data.answer || 'No response received.' },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: `⚠️ AI service returned an error (${res.status}). The AI Copilot backend may not be running yet. Please ensure Ollama is active.`,
          },
        ]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: '⚠️ Could not reach the AI service. Make sure the backend is running and the AI Copilot endpoint is configured.',
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleExampleClick = (query) => {
    setInput(query);
    inputRef.current?.focus();
  };

  return (
    <div className="w-80 shrink-0 bg-bg-elevated border-l border-border-primary flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="h-10 px-3 flex items-center justify-between border-b border-border-primary shrink-0">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-accent" />
          <h2 className="text-base font-semibold text-text-bright">AI Assistant</h2>
        </div>
        <button onClick={onClose} className="p-1 rounded text-text-secondary hover:text-text-bright hover:bg-bg-hover transition-colors">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3 scrollbar-thin">
        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'assistant' && (
              <div className="w-6 h-6 rounded-full bg-accent/15 flex items-center justify-center shrink-0 mt-0.5">
                <Bot className="w-3.5 h-3.5 text-accent" />
              </div>
            )}
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap ${
                msg.role === 'user'
                  ? 'bg-accent text-white rounded-br-sm'
                  : 'bg-bg-hover text-text-primary rounded-bl-sm'
              }`}
            >
              {msg.content}
            </div>
            {msg.role === 'user' && (
              <div className="w-6 h-6 rounded-full bg-bg-hover flex items-center justify-center shrink-0 mt-0.5">
                <User className="w-3.5 h-3.5 text-text-secondary" />
              </div>
            )}
          </div>
        ))}

        {isLoading && (
          <div className="flex gap-2 justify-start">
            <div className="w-6 h-6 rounded-full bg-accent/15 flex items-center justify-center shrink-0 mt-0.5">
              <Bot className="w-3.5 h-3.5 text-accent" />
            </div>
            <div className="bg-bg-hover rounded-lg px-3 py-2 rounded-bl-sm">
              <Loader2 className="w-4 h-4 text-text-muted animate-spin" />
            </div>
          </div>
        )}

        {!isChecking && !isOnline && (
          <div className="mt-4 p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-center">
            <h3 className="text-sm font-semibold text-red-400 mb-2">⚠️ AI Offline</h3>
            <p className="text-xs text-text-secondary mb-3 leading-relaxed">
              Ollama is not initiated. AI features are not available. Please start Ollama on your system.
            </p>
            <button 
              onClick={checkStatus}
              className="text-xs bg-red-500/20 hover:bg-red-500/30 text-red-300 px-3 py-1.5 rounded-md transition-colors"
            >
              Refresh Connection
            </button>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Example chips — only show when conversation is fresh */}
      {messages.length <= 1 && (
        <div className="px-3 pb-2 flex flex-wrap gap-1.5">
          {EXAMPLE_QUERIES.map((q, i) => (
            <button
              key={i}
              onClick={() => handleExampleClick(q)}
              className="text-xs px-2 py-1 rounded-full bg-bg-hover text-text-secondary hover:text-accent hover:bg-accent/10 border border-border-secondary transition-colors truncate max-w-full"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="p-2 border-t border-border-primary shrink-0">
        <div className={`flex items-end gap-2 bg-bg-secondary rounded-lg border px-2 py-1.5 transition-colors ${!isOnline ? 'border-red-500/30 opacity-60' : 'border-border-secondary focus-within:border-accent'}`}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={!isOnline}
            placeholder={isOnline ? "Ask about alerts, detections..." : "AI is offline..."}
            rows={1}
            className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted resize-none outline-none max-h-20 scrollbar-thin disabled:cursor-not-allowed"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading || !isOnline}
            className="p-1.5 rounded-md bg-accent text-white hover:bg-accent-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
