import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { AlertCircle, Loader2, Search, Plus, Navigation, Layers, X, Trash2, Film, CheckCircle2 } from 'lucide-react';
import { getApiBase, getApiKey, toggleVideoScan } from '../services/api';
import VideoManagementModal from '../components/VideoManagementModal';

export default function VideoFileWall() {
  const [activeVideos, setActiveVideos] = useState(() => {
    try {
      const saved = localStorage.getItem('videowall_activeVideos');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [manageModalOpen, setManageModalOpen] = useState(false);

  const loadData = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${getApiBase()}/videos/list?api_key=${encodeURIComponent(getApiKey() || "")}`);
      if (!res.ok) throw new Error('Failed to load videos');
      const data = await res.json();
      setVideos(data || []);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to load videos');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  useEffect(() => {
    localStorage.setItem('videowall_activeVideos', JSON.stringify(activeVideos));
    window.dispatchEvent(new CustomEvent('videowall_videos_changed'));
  }, [activeVideos]);

  const handleToggleVideo = useCallback((video) => {
    setActiveVideos(prev => {
      const exists = prev.find(v => v.id === video.id);
      const newActive = exists ? prev.filter(v => v.id !== video.id) : [...prev, video];
      localStorage.setItem('videowall_activeVideos', JSON.stringify(newActive));
      window.dispatchEvent(new CustomEvent('videowall_videos_changed'));
      return newActive;
    });
  }, []);

  const handleRemoveActive = useCallback((id) => {
    setActiveVideos(prev => {
      const newActive = prev.filter(v => v.id !== id);
      localStorage.setItem('videowall_activeVideos', JSON.stringify(newActive));
      window.dispatchEvent(new CustomEvent('videowall_videos_changed'));
      return newActive;
    });
  }, []);

  const handleClearWall = () => {
    setActiveVideos([]);
    localStorage.setItem('videowall_activeVideos', JSON.stringify([]));
    window.dispatchEvent(new CustomEvent('videowall_videos_changed'));
  };
  
  const handleLoadAllFiltered = () => {
    setActiveVideos(prev => {
      const newActive = [...prev];
      const activeIds = new Set(newActive.map(v => v.id));
      filteredVideos.forEach(vid => {
        if (!activeIds.has(vid.id)) {
          newActive.push(vid);
        }
      });
      localStorage.setItem('videowall_activeVideos', JSON.stringify(newActive));
      window.dispatchEvent(new CustomEvent('videowall_videos_changed'));
      return newActive;
    });
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Are you sure you want to delete this video?')) return;
    try {
      setLoading(true);
      const res = await fetch(`${getApiBase()}/videos/delete/${id}?api_key=${encodeURIComponent(getApiKey() || "")}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Delete failed');
      setActiveVideos(prev => prev.filter(v => v.id !== id));
      await loadData();
      alert('Video deleted successfully!');
    } catch (err) {
      alert(`Delete failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const activeVideoIds = useMemo(() => new Set(activeVideos.map(v => v.id)), [activeVideos]);
  const filteredVideos = useMemo(() => {
    return videos.filter(vid => {
      if (activeVideoIds.has(vid.id)) return false;
      const q = searchQuery.toLowerCase();
      return !q || vid.filename.toLowerCase().includes(q);
    });
  }, [videos, searchQuery, activeVideoIds]);

  const count = activeVideos.length;
  const cols = count > 0 ? Math.min(4, Math.ceil(Math.sqrt(count))) : 1;
  const rows = count > 0 ? Math.ceil(count / cols) : 1;

  return (
    <div className="h-full flex bg-bg-primary overflow-hidden relative">
      <VideoManagementModal isOpen={manageModalOpen} onClose={() => setManageModalOpen(false)} onUploaded={() => loadData()} />

      <div className="w-[260px] flex flex-col bg-bg-elevated border-r border-border-primary shrink-0 relative z-50 shadow-sm">
        <div className="p-3 border-b border-border-secondary shrink-0 relative z-50">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-bold text-text-secondary uppercase tracking-wider truncate mr-2">
              Videos ({videos.length}) {loading && <Loader2 className="w-3 h-3 animate-spin inline ml-2 text-accent" />}
            </h2>
            <button onClick={() => setManageModalOpen(true)} className="w-6 h-6 flex items-center justify-center rounded text-text-secondary hover:text-accent hover:bg-bg-hover">
              <Plus className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="relative w-full mt-2 flex items-center">
            <input 
              type="text" placeholder="Search videos..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} 
              className="block w-full pl-3.5 pr-10 py-2.5 border border-transparent rounded-full bg-bg-primary text-text-primary placeholder-text-muted text-sm font-medium focus:outline-none focus:border-accent focus:bg-white focus:ring-1 focus:ring-accent transition-all" 
            />
            {searchQuery && (
              <>
                <div className="absolute right-8 h-4 w-[1px] bg-border-secondary pointer-events-none" />
                <button type="button" onClick={() => setSearchQuery('')} className="absolute right-1 w-6 h-6 flex items-center justify-center rounded-full text-text-muted hover:text-text-primary hover:bg-bg-hover">
                  <X className="w-3.5 h-3.5" strokeWidth={2.5} />
                </button>
              </>
            )}
          </div>
          <div className="flex gap-2 mt-3">
            {filteredVideos.some(vid => !activeVideoIds.has(vid.id)) && (
              <button onClick={handleLoadAllFiltered} className="flex-1 py-1.5 flex items-center justify-center gap-1.5 bg-accent/10 hover:bg-accent/20 text-accent rounded text-xs font-semibold transition-colors">
                <Layers className="w-3.5 h-3.5" /> Load All
              </button>
            )}
            {activeVideos.length > 0 && (
              <button onClick={handleClearWall} className="flex-1 py-1.5 flex items-center justify-center gap-1.5 bg-danger/10 hover:bg-danger/20 text-danger rounded text-xs font-semibold transition-colors">
                <Layers className="w-3.5 h-3.5" /> Remove All
              </button>
            )}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-2 relative">
          {error ? (
            <div className="flex items-center gap-2 text-danger text-sm p-3 bg-danger/10 rounded-md"><AlertCircle className="w-4 h-4 shrink-0" /><span>{error}</span></div>
          ) : videos.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 text-center"><Navigation className="w-8 h-8 text-text-muted mb-2 opacity-50" /><p className="text-sm text-text-secondary">No videos found.</p></div>
          ) : (
            <>{(() => {
            const allVideos = [...activeVideos.map(v => ({ ...v, _isActive: true })), ...filteredVideos.map(v => ({ ...v, _isActive: false }))];
            return allVideos.map(vid => {
              const isActive = vid._isActive;
              return (
                <div
                  key={vid.id}
                  onClick={() => handleToggleVideo(vid)}
                  className={`group bg-bg-elevated border rounded-md p-2.5 transition-all duration-150 select-none cursor-pointer
                    ${isActive ? 'border-accent shadow-[0_0_0_1px_rgba(37,99,235,0.4)]' : 'border-border-secondary hover:bg-bg-hover hover:border-border-primary'}
                  `}
                >
                  {/* Top Row */}
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 min-w-0 flex-1">
                      {isActive ? (
                        <CheckCircle2 className="w-4 h-4 text-accent shrink-0" />
                      ) : (
                        <Film className="w-4 h-4 text-text-muted shrink-0" />
                      )}
                      <span className={`font-bold text-sm truncate ${isActive ? 'text-accent' : 'text-text-primary'}`}>
                        {vid.filename}
                      </span>
                    </div>
                  </div>

                  {/* Bottom Row */}
                  <div className="mt-2 flex items-center justify-between gap-2 text-xs text-text-muted pl-[22px] min-h-[20px]">
                    <span className="truncate">{new Date(vid.uploaded_at).toLocaleDateString()}</span>
                    <div className="hidden group-hover:flex items-center gap-1">
                      <button
                        className="p-1 rounded text-text-muted hover:text-danger hover:bg-danger/10 transition-colors"
                        title="Delete Video"
                        onClick={(e) => { e.stopPropagation(); handleDelete(vid.id); }}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            });
          })()}</>
          )}
        </div>
      </div>

      <div className="flex-1 p-3 overflow-y-auto bg-bg-primary flex flex-col">
        {count === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center border-2 border-dashed border-border-primary rounded-xl m-4 bg-bg-secondary/50 text-center">
            <Layers className="w-12 h-12 text-text-muted mb-4 opacity-50" />
            <h3 className="text-lg font-semibold text-text-secondary mb-1">
              Click a video to play
            </h3>
          </div>
        ) : (
          <div className={`w-full grid gap-2 ${count <= 16 ? 'h-full' : ''}`} style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gridTemplateRows: count <= 16 ? `repeat(${rows}, minmax(0, 1fr))` : 'none', gridAutoRows: count > 16 ? 'minmax(200px, 25vh)' : 'auto' }}>
            {activeVideos.map((video, index) => (
              <div key={video.id} className="relative isolate group w-full h-full bg-black overflow-hidden rounded-lg border border-border-primary">
                <video
                  src={`${getApiBase()}/videos/play/${video.id}?api_key=${encodeURIComponent(getApiKey() || "")}`}
                  className="w-full h-full object-contain"
                  controls
                  playsInline
                  onEnded={async () => {
                    try {
                      await toggleVideoScan(video.id, false);
                      window.dispatchEvent(new CustomEvent('ai_status_changed'));
                    } catch (err) {
                      console.error('Failed to terminate AI scan on video end:', err);
                    }
                  }}
                />
                <button onClick={() => handleRemoveActive(video.id)} className="absolute top-1.5 right-1.5 p-1 bg-danger/80 hover:bg-danger text-white rounded backdrop-blur-sm transition-colors opacity-0 group-hover:opacity-100 z-10" title="Remove video"><X className="w-3.5 h-3.5" /></button>
                <div className="absolute top-1.5 left-1.5 z-10 px-1.5 py-0.5 bg-black/50 rounded backdrop-blur-sm pointer-events-none text-white font-bold text-xs truncate max-w-[80%]">{video.filename}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
