import { useState } from 'react';
import { X, Plus, Bell, ShieldAlert, Bot, RefreshCw } from 'lucide-react';
import { useLocation } from 'react-router-dom';

export default function Navbar({ alertCount = 0, onToggleAlertPanel, onToggleAIPanel, rightPanel, onOpenAddCamera }) {
  const [searchValue, setSearchValue] = useState('');
  const location = useLocation();
  
  const getPageTitle = () => {
    switch (location.pathname) {
      case '/': return 'Dashboard';
      case '/live': return 'Video Wall';
      case '/registry': return 'GIS Registry';
      case '/logs': return 'Live Logs';
      case '/playback': return 'Playback';
      default: return '';
    }
  };

  const title = getPageTitle();

  return (
    <header className="h-12 bg-bg-secondary border-b border-border-primary flex items-center justify-between px-4 shrink-0 z-40 select-none">
      <div className="flex items-center flex-1 min-w-0">
        <h1 className="text-lg font-bold text-text-bright tracking-tight truncate flex items-center gap-2">
          <span>Gujarat <span className="text-accent">Sentinel</span></span>
          {title && (
            <>
              <span className="text-text-muted text-sm font-medium">&gt;</span>
              <span className="text-sm font-medium text-text-primary">{title}</span>
            </>
          )}
        </h1>
      </div>
      <div className="flex items-center justify-center flex-1 space-x-1">
        <button onClick={() => window.location.reload()} className="w-7 h-7 shrink-0 flex items-center justify-center rounded text-text-secondary hover:text-text-bright hover:bg-bg-hover transition-colors" title="Refresh">
          <RefreshCw className="w-4 h-4" />
        </button>

        <div className="relative w-full max-w-sm flex items-center">
          <input
            type="text"
            placeholder="Search camera id..."
            value={searchValue}
            onChange={(e) => setSearchValue(e.target.value)}
            className="navbar-search-input block w-full pl-3.5 pr-10 py-1.5 border border-transparent rounded-full bg-bg-primary text-text-primary placeholder-text-muted text-sm font-medium focus:outline-none focus:border-accent focus:bg-white focus:ring-1 focus:ring-accent transition-all"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                window.dispatchEvent(new CustomEvent('globalSearch', { detail: searchValue }));
              }
            }}
          />
          {searchValue && (
            <>
              {/* Divider just next to clear icon on the left */}
              <div className="absolute right-8 h-4 w-[1px] bg-border-primary pointer-events-none" />
              <button
                type="button"
                className="absolute right-1 w-6 h-6 flex items-center justify-center rounded-full text-text-muted hover:text-text-primary hover:bg-bg-hover transition-colors"
                title="Clear Search"
                onClick={() => {
                  setSearchValue('');
                  window.dispatchEvent(new CustomEvent('globalSearch', { detail: '' }));
                }}
              >
                <X className="w-3.5 h-3.5" strokeWidth={2.5} />
              </button>
            </>
          )}
        </div>

        <button 
          onClick={() => {
            if (onOpenAddCamera) {
              onOpenAddCamera();
            } else {
              window.dispatchEvent(new CustomEvent('openManageCameras'));
            }
          }}
          className="w-7 h-7 shrink-0 flex items-center justify-center rounded text-text-secondary hover:text-text-bright hover:bg-bg-hover transition-colors" 
          title="Add Camera"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>
      <div className="flex items-center justify-end flex-1 gap-2">
        <div id="navbar-actions-portal" className="flex items-center gap-1 empty:hidden border-r border-border-primary pr-3 mr-1"></div>
        <div className="flex items-center gap-0.5">
          <button className="w-7 h-7 flex items-center justify-center rounded text-text-secondary hover:text-text-bright hover:bg-bg-hover transition-colors relative" title="Notifications">
            <Bell className="w-4 h-4" />
          </button>
          <button onClick={onToggleAIPanel} className={`w-7 h-7 flex items-center justify-center rounded transition-colors relative ${rightPanel === 'ai' ? 'text-accent bg-bg-active' : 'text-text-secondary hover:text-accent hover:bg-bg-hover'}`} title="AI Assistant">
            <Bot className="w-4 h-4" />
          </button>
          <button onClick={onToggleAlertPanel} className={`w-7 h-7 flex items-center justify-center rounded transition-colors relative ${rightPanel === 'alerts' ? 'text-warning bg-bg-active' : 'text-text-secondary hover:text-warning hover:bg-bg-hover'}`} title="Live Alerts">
            <ShieldAlert className="w-4 h-4" />
            {alertCount > 0 && <span className="absolute -top-0.5 -right-0.5 min-w-[14px] h-[14px] px-0.5 flex items-center justify-center text-[9px] font-bold bg-danger text-white rounded-full">{alertCount > 99 ? '99+' : alertCount}</span>}
          </button>
        </div>
      </div>
    </header>
  );
}
