import { X, Bot } from 'lucide-react';

export default function AIPanel({ onClose }) {
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

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 flex flex-col items-center justify-center text-center space-y-2">
        <Bot className="w-8 h-8 text-text-secondary" />
        <p className="text-base font-medium text-text-secondary">AI Assistant coming soon!</p>
        <p className="text-sm font-medium text-text-secondary">You will be able to ask questions and control cameras here.</p>
      </div>
    </div>
  );
}
