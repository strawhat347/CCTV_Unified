import { useEffect, useRef } from 'react';
import { logout, getCurrentUser } from '../services/api';
import { User, LogOut, Settings, Moon, Activity, History, Users } from 'lucide-react';

export default function SettingsPopup({ sidebarOpen, onClose }) {
  const ref = useRef(null);

  // Close on click-outside
  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) {
        onClose();
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [onClose]);

  const toggleTheme = () => {
    document.documentElement.classList.toggle('light');
  };

  return (
    <div
      ref={ref}
      className={`absolute bottom-full mb-1.5 ${sidebarOpen ? 'left-1.5 w-60' : 'left-1.5 w-56'} bg-bg-elevated border border-border-secondary rounded-lg shadow-2xl z-[100] overflow-hidden whitespace-nowrap`}
    >
      {/* Account section */}
      <div className="px-3 py-2.5 border-b border-border-primary">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-accent flex items-center justify-center shrink-0">
            <User className="w-3.5 h-3.5 text-white" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-text-bright truncate capitalize">{getCurrentUser()?.username || 'User'}</p>
            <p className="text-xs text-text-secondary truncate capitalize">{getCurrentUser()?.role || 'Guest'} Role</p>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="px-1.5 py-1.5 border-b border-border-primary">
        <button 
          onClick={toggleTheme}
          className="flex items-center gap-2 w-full px-2 py-1.5 rounded text-sm text-left text-text-secondary hover:text-text-bright hover:bg-bg-hover transition-colors"
        >
          <Moon className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">Toggle Theme</span>
        </button>
        <button className="flex items-center gap-2 w-full px-2 py-1.5 rounded text-sm text-left text-text-secondary hover:text-text-bright hover:bg-bg-hover transition-colors">
          <Activity className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">System Health</span>
        </button>
        <button className="flex items-center gap-2 w-full px-2 py-1.5 rounded text-sm text-left text-text-secondary hover:text-text-bright hover:bg-bg-hover transition-colors">
          <History className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">Audit Logs</span>
        </button>
        <button className="flex items-center gap-2 w-full px-2 py-1.5 rounded text-sm text-left text-text-secondary hover:text-text-bright hover:bg-bg-hover transition-colors">
          <Users className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">User Management</span>
        </button>
      </div>

      {/* Settings */}
      <div className="px-1.5 py-1.5">
        <button
          className="flex items-center gap-2 w-full px-2 py-1.5 rounded text-sm text-left text-text-secondary hover:text-text-bright hover:bg-bg-hover transition-colors"
        >
          <Settings className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">Settings</span>
        </button>
      </div>

      {/* Sign out */}
      <div className="px-1.5 py-1.5 border-t border-border-primary">
        <button
          onClick={() => { logout(); window.location.reload(); }}
          className="flex items-center gap-2 w-full px-2 py-1.5 rounded text-sm text-left text-text-secondary hover:text-danger hover:bg-bg-hover transition-colors"
        >
          <LogOut className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">Sign Out</span>
        </button>
      </div>
    </div>
  );
}


