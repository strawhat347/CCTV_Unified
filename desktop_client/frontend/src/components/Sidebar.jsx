import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  PanelLeftClose, PanelLeftOpen,
  LayoutDashboard, Video, Map, PlaySquare,
  User, ScrollText
} from 'lucide-react';
import SettingsPopup from './SettingsPopup';

const navItems = [
  { id: 'dashboard', path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'live', path: '/live', label: 'Live View', icon: Video },
  { id: 'registry', path: '/registry', label: 'GIS & Registry', icon: Map },
  { id: 'logs', path: '/logs', label: 'Live Logs', icon: ScrollText },
  { id: 'playback', path: '/playback', label: 'Playback', icon: PlaySquare },
];

export default function Sidebar({ isOpen, toggleSidebar }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [showSettings, setShowSettings] = useState(false);

  return (
    <nav className={`absolute left-0 top-0 bottom-0 ${isOpen ? 'w-52 shadow-xl' : 'w-12'} bg-bg-secondary flex flex-col border-r border-border-primary transition-all duration-200 z-50 shrink-0 select-none`}>

      {/* ── Top Controls ─────────────────────────── */}
      <div className={`h-11 flex items-center ${isOpen ? 'justify-between px-2' : 'justify-center'} shrink-0`}>
        {/* Sidebar toggle */}
        <button
          onClick={toggleSidebar}
          className="p-1.5 rounded text-text-secondary hover:text-text-bright hover:bg-bg-hover transition-colors"
          title={isOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        >
          {isOpen ? <PanelLeftClose className="w-4 h-4" /> : <PanelLeftOpen className="w-4 h-4" />}
        </button>
      </div>

      {/* ── Nav Items ────────────────────────────── */}
      <ul className="flex-1 py-1 space-y-0.5 overflow-y-auto px-1.5">
        {navItems.map(({ id, path, label, icon: Icon }) => {
          // dashboard is special since it's the root path '/'
          const active = path === '/' ? location.pathname === '/' : location.pathname.startsWith(path);
          return (
            <li
              key={id}
              onClick={() => navigate(path)}
              className={`group flex items-center gap-3 rounded-md cursor-pointer transition-colors
                ${isOpen ? 'px-2.5 py-1.5' : 'justify-center py-2'}
                ${active
                  ? 'bg-bg-active text-text-bright'
                  : 'text-text-secondary hover:bg-bg-hover hover:text-text-bright'
                }`}
              title={!isOpen ? label : undefined}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {isOpen && <span className="text-base font-medium truncate">{label}</span>}
            </li>
          );
        })}
      </ul>

      {/* ── Bottom: Account ─────────────────────── */}
      <div className="border-t border-border-primary px-1.5 py-1.5 relative">
        <button
          onClick={() => setShowSettings(!showSettings)}
          className={`flex items-center gap-3 w-full rounded-md transition-colors
            ${isOpen ? 'px-2.5 py-1.5' : 'justify-center py-2'}
            ${showSettings
              ? 'bg-bg-active text-text-bright'
              : 'text-text-secondary hover:bg-bg-hover hover:text-text-bright'
            }`}
          title="Account"
        >
          <User className="w-4 h-4 shrink-0" />
          {isOpen && <span className="text-base font-medium">Account</span>}
        </button>

        {/* Settings Popup (like VS Code / Windows Start) */}
        {showSettings && (
          <SettingsPopup
            sidebarOpen={isOpen}
            onClose={() => setShowSettings(false)}
          />
        )}
      </div>
    </nav>
  );
}
