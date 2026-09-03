import { useState, useEffect, useRef, useCallback } from 'react';
import { X, Plus, Bell, ShieldAlert, Bot, RefreshCw, Power, Cpu } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { toggleScan, fetchSystemStatus } from '../services/api';

export default function Navbar({ alertCount = 0, onToggleAlertPanel, onToggleAIPanel, rightPanel, onOpenAddCamera }) {
  const [searchValue, setSearchValue] = useState('');
  const [isScanning, setIsScanning] = useState(false);
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [scanMenuOpen, setScanMenuOpen] = useState(false);
  const scanCardRef = useRef(null);
  const scanButtonRef = useRef(null);
  const [activeAICameras, setActiveAICameras] = useState([]);
  const [activeAIVideos, setActiveAIVideos] = useState([]);
  const [wallCameras, setWallCameras] = useState([]);
  const [wallVideos, setWallVideos] = useState([]);
  const location = useLocation();

  useEffect(() => {
    if (!scanMenuOpen) return;
    const handleClickOutside = (e) => {
      if (
        scanCardRef.current && 
        !scanCardRef.current.contains(e.target) &&
        scanButtonRef.current && 
        !scanButtonRef.current.contains(e.target)
      ) {
        setScanMenuOpen(false);
      }
    };
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        setScanMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [scanMenuOpen]);
  
  const syncWallCameras = () => {
    try {
      const saved = localStorage.getItem('videowall_activeCameras');
      setWallCameras(saved ? JSON.parse(saved) : []);
    } catch (e) { console.error(e); }
  };

  const syncWallVideos = () => {
    try {
      const saved = localStorage.getItem('videowall_activeVideos');
      setWallVideos(saved ? JSON.parse(saved) : []);
    } catch (e) { console.error(e); }
  };

  const refreshSystemStatus = useCallback(() => {
    fetchSystemStatus()
      .then(status => {
        setIsScanning(status.workers_active);
        setActiveAICameras(status.active_cameras || []);
        setActiveAIVideos(status.active_videos || []);
      })
      .catch(err => console.error("Failed to fetch system status:", err));
  }, []);

  useEffect(() => {
    syncWallCameras();
    window.addEventListener('videowall_cameras_changed', syncWallCameras);
    return () => window.removeEventListener('videowall_cameras_changed', syncWallCameras);
  }, []);

  useEffect(() => {
    syncWallVideos();
    window.addEventListener('videowall_videos_changed', syncWallVideos);
    return () => window.removeEventListener('videowall_videos_changed', syncWallVideos);
  }, []);

  useEffect(() => {
    syncWallCameras();
    syncWallVideos();
    refreshSystemStatus();
    window.addEventListener('ai_status_changed', refreshSystemStatus);
    const interval = setInterval(refreshSystemStatus, 3000);
    return () => {
      window.removeEventListener('ai_status_changed', refreshSystemStatus);
      clearInterval(interval);
    };
  }, [location.pathname, scanMenuOpen, refreshSystemStatus]);

  const handleToggleScan = async () => {
    if (isTransitioning) return;
    setIsTransitioning(true);
    const targetState = !isScanning;
    try {
      await toggleScan(targetState);
      setIsScanning(targetState);
      if (!targetState) {
        setActiveAICameras([]);
        setActiveAIVideos([]);
      }
    } catch (err) {
      console.error("Failed to toggle scan:", err);
    } finally {
      setIsTransitioning(false);
    }
  };
  
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
    <header className="h-12 bg-bg-secondary border-b border-border-primary flex items-center justify-between px-4 shrink-0 relative z-[60] select-none">
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
        <div className="flex items-center gap-0.5 relative">
          {(location.pathname.startsWith('/live') || location.pathname.startsWith('/logs')) && (
            <>
              {/* Assign AI Button (Only visible on Feeds when Power is ON) */}
              {isScanning && location.pathname.startsWith('/live') && (
                <div className="relative mr-1">
                  <button 
                    ref={scanButtonRef}
                    onClick={() => setScanMenuOpen(!scanMenuOpen)} 
                    className="flex items-center justify-center gap-1.5 px-2 h-7 rounded text-xs font-medium transition-colors text-text-secondary hover:text-accent hover:bg-bg-hover border border-border-secondary"
                    title="Assign AI"
                  >
                    <Cpu className="w-3.5 h-3.5" />
                    <span>Assign AI</span>
                  </button>
                  
                  {scanMenuOpen && (() => {
                    const isVideoMode = location.pathname.startsWith('/live/videos');
                    const items = isVideoMode ? wallVideos : wallCameras;
                    const activeItems = isVideoMode ? activeAIVideos : activeAICameras;
                    const setActiveItems = isVideoMode ? setActiveAIVideos : setActiveAICameras;
                    const title = isVideoMode ? "Videos" : "Cameras";
                    const idField = isVideoMode ? "id" : "camera_id";
                    const nameField = isVideoMode ? "filename" : "name";

                    return (
                      <>
                        {/* Backdrop to close the card when clicking anywhere outside */}
                        <div 
                          className="fixed inset-0 z-40" 
                          onClick={() => setScanMenuOpen(false)} 
                        />
                        <div 
                          ref={scanCardRef}
                          className="absolute right-0 top-full mt-2 w-80 bg-bg-elevated border border-border-secondary rounded-lg shadow-2xl z-50 overflow-hidden flex flex-col"
                        >
                          <div className="p-3 border-b border-border-secondary bg-bg-secondary flex justify-between items-center">
                            <span className="font-semibold text-sm text-text-primary">Assign AI to {title}</span>
                            <button onClick={() => setScanMenuOpen(false)} className="text-text-muted hover:text-text-primary">
                              <X className="w-4 h-4" />
                            </button>
                          </div>
                          <div className="max-h-72 overflow-y-auto p-2">
                            {items.length === 0 ? (
                              <div className="text-xs text-text-muted text-center py-4">No {title.toLowerCase()} in Video Wall</div>
                            ) : (
                              <>
                                <button 
                                  onClick={async () => {
                                    const allScanning = items.every(item => activeItems.includes(item[idField]));
                                    const newState = !allScanning;
                                    
                                    // Optimistic update
                                    setActiveItems(prev => {
                                      let updated = [...prev];
                                      if (newState) {
                                        items.forEach(item => { if (!updated.includes(item[idField])) updated.push(item[idField]); });
                                      } else {
                                        const ids = items.map(i => i[idField]);
                                        updated = updated.filter(id => !ids.includes(id));
                                      }
                                      return updated;
                                    });

                                    try {
                                      const api = await import('../services/api');
                                      const toggleFn = isVideoMode ? api.toggleVideoScan : api.toggleCameraScan;
                                      await Promise.all(items.map(item => toggleFn(item[idField], newState)));
                                      const status = await api.fetchSystemStatus();
                                      setIsScanning(status.workers_active);
                                    } catch(e) { 
                                      console.error("Toggle all error", e);
                                    }
                                  }}
                                  className={`w-full py-1.5 text-xs font-medium rounded transition-colors bg-bg-secondary hover:bg-bg-hover text-text-primary border border-border-primary`}
                                >
                                  {items.every(item => activeItems.includes(item[idField])) ? 'Deassign All' : 'Assign All'}
                                </button>
                                <div className="h-px bg-border-secondary my-2"></div>
                                {items.map(item => {
                                  const itemId = item[idField];
                                  const itemIsScanning = activeItems.includes(itemId);
                                  const itemName = item[nameField] || (isVideoMode ? 'Video' : 'Camera');
                                  return (
                                    <div key={itemId} className="flex items-center justify-between p-2 rounded hover:bg-bg-hover gap-3 transition-colors">
                                      <div className="flex-1 min-w-0 pr-1">
                                        <span 
                                          className="text-xs font-medium text-text-primary block truncate select-none"
                                          title={`#${itemId} - ${itemName}`}
                                        >
                                          #{itemId} - {itemName}
                                        </span>
                                      </div>
                                      <button
                                        type="button"
                                        onClick={async (e) => {
                                          e.stopPropagation();
                                          const newState = !itemIsScanning;
                                          // Optimistic update
                                          setActiveItems(prev => newState ? [...prev, itemId] : prev.filter(id => id !== itemId));
                                          try {
                                            const api = await import('../services/api');
                                            const toggleFn = isVideoMode ? api.toggleVideoScan : api.toggleCameraScan;
                                            await toggleFn(itemId, newState);
                                            const status = await api.fetchSystemStatus();
                                            setIsScanning(status.workers_active);
                                          } catch (err) { 
                                            console.error("Toggle error:", err);
                                            setActiveItems(prev => !newState ? [...prev, itemId] : prev.filter(id => id !== itemId));
                                          }
                                        }}
                                        className={`shrink-0 w-10 h-5 rounded-full relative transition-colors cursor-pointer focus:outline-none ${
                                          itemIsScanning ? 'bg-success' : 'bg-bg-secondary border border-border-primary'
                                        }`}
                                        title={itemIsScanning ? "Stop AI Scan" : "Start AI Scan"}
                                      >
                                        <div className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-transform duration-200 pointer-events-none ${
                                          itemIsScanning ? 'translate-x-5' : 'translate-x-0'
                                        }`}></div>
                                      </button>
                                    </div>
                                  );
                                })}
                              </>
                            )}
                          </div>
                        </div>
                      </>
                    );
                  })()}
                </div>
              )}

              {/* Master Power Button */}
              <button 
                onClick={handleToggleScan}
                disabled={isTransitioning}
                className={`w-7 h-7 flex items-center justify-center rounded transition-all ${
                  isTransitioning
                    ? (isScanning ? 'text-white bg-success opacity-50 cursor-not-allowed animate-pulse' : 'text-text-secondary opacity-50 cursor-not-allowed animate-pulse')
                    : isScanning 
                      ? 'text-white bg-success hover:bg-green-600 shadow-sm' 
                      : 'text-text-secondary hover:text-accent hover:bg-bg-hover'
                }`}
                title={
                  isTransitioning 
                    ? (isScanning ? 'Stopping Master AI Engine...' : 'Starting Master AI Engine...')
                    : (isScanning ? 'Stop Master AI Engine' : 'Start Master AI Engine')
                }
              >
                <Power className="w-4 h-4" />
              </button>
              
              <div className="h-4 w-[1px] bg-border-primary mx-1" />
            </>
          )}

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
