import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { createPortal } from 'react-dom';
import { AlertCircle, Loader2, Search, Plus, Navigation, Filter, Layers, X } from 'lucide-react';
import { fetchCameras, fetchStreamMode, importCamerasCsv, deleteAllCameras, addCamera, deleteSingleCamera, updateCamera } from '../services/api';
import VideoCell from '../components/VideoCell';
import CameraListCard from '../components/CameraListCard';
import CameraManagementModal from '../components/CameraManagementModal';
import EditCameraModal from '../components/EditCameraModal';
import { toast } from '../components/Toast';
import { confirmModal } from '../components/ConfirmModal';

const STORAGE_KEY_ACTIVE = 'videowall_activeCameras';
const STORAGE_KEY_SEARCH = 'videowall_searchQuery';
const STORAGE_KEY_DISTRICT = 'videowall_districtFilter';
const STORAGE_KEY_OFFSET = 'videowall_offset';

export default function VideoWall() {
  const [activeCameras, setActiveCameras] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY_ACTIVE);
      if (!saved) return [];
      const parsed = JSON.parse(saved);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  });
  
  const [cameras, setCameras] = useState([]);
  const [streamMode, setStreamMode] = useState('mjpeg');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [offset, setOffset] = useState(() => {
    try { return parseInt(localStorage.getItem(STORAGE_KEY_OFFSET) || '0', 10); } catch { return 0; }
  });
  const [hasMore, setHasMore] = useState(true);
  const [searchQuery, setSearchQuery] = useState(() => localStorage.getItem(STORAGE_KEY_SEARCH) || '');
  const [districtFilter, setDistrictFilter] = useState(() => localStorage.getItem(STORAGE_KEY_DISTRICT) || 'all'); 
  const [filterMenuOpen, setFilterMenuOpen] = useState(false);
  const [manageModalOpen, setManageModalOpen] = useState(false);
  const [editingCamera, setEditingCamera] = useState(null);
  const [portalNode, setPortalNode] = useState(null);
  
  useEffect(() => setPortalNode(document.getElementById('navbar-actions-portal')), []);

  const loadDataRef = useRef();
  const setSearchQueryRef = useRef();

  const loadData = useCallback(async (reset = false, query = searchQuery) => {
    try {
      if (reset) { setLoading(true); setOffset(0); }
      const currentOffset = reset ? 0 : offset;
      const [cams, modeResult] = await Promise.all([
        fetchCameras(null, query, 50, currentOffset),
        fetchStreamMode().catch(() => ({ mode: 'mjpeg' }))
      ]);
      if (reset) setCameras(cams || []);
      else setCameras(prev => [...prev, ...(cams || [])]);
      setHasMore(cams?.length === 50);
      setStreamMode(modeResult?.mode || 'mjpeg');
      setError(null);
    } catch (err) { setError(err.message || 'Failed to load cameras'); } 
    finally { if (reset) setLoading(false); }
  }, [offset, searchQuery]);

  useEffect(() => {
    loadDataRef.current = loadData;
    setSearchQueryRef.current = setSearchQuery;
  }, [loadData, setSearchQuery]);

  useEffect(() => {
    const handleGlobalSearch = (e) => { if (setSearchQueryRef.current) setSearchQueryRef.current(e.detail); };
    const handleCamerasChanged = () => { if (loadDataRef.current) loadDataRef.current(true); };
    window.addEventListener('globalSearch', handleGlobalSearch);
    const handleLaunchVideoWall = async (e) => {
      const cameraIdsToLaunch = e.detail; // Array of IDs
      if (!cameraIdsToLaunch || cameraIdsToLaunch.length === 0) return;
      
      try {
        // Fetch full camera objects since we only have IDs
        const newCameras = [];
        for (const id of cameraIdsToLaunch) {
          // We can fetch from API or if they are in the current `cameras` state, use those
          // But since `cameras` state is paginated, it's safer to fetch. Wait, we can fetch from backend
          // Since there is no bulk fetch, we can just use `fetchCameras` with a large limit or individually
        }
      } catch (err) {
        console.error("Failed to launch video wall", err);
      }
    };
    
    // Wait, simpler way: VideoWall already has `cameras` which might not have all of them if paginated.
    // Let's implement a listener that just adds whatever it can find, or fetches them.
  }, []);

  useEffect(() => { loadData(true); }, []);
  const isInitialMount = useRef(true);

  useEffect(() => {
    if (isInitialMount.current) { isInitialMount.current = false; return; }
    const timer = setTimeout(() => { if (loadDataRef.current) loadDataRef.current(true, searchQuery); }, 500);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const loadMore = () => setOffset(prev => prev + 50);
  
  useEffect(() => {
    if (offset > 0 && loadDataRef.current) loadDataRef.current(false, searchQuery);
  }, [offset, searchQuery]);

  useEffect(() => { 
    localStorage.setItem(STORAGE_KEY_ACTIVE, JSON.stringify(activeCameras)); 
    window.dispatchEvent(new Event('videowall_cameras_changed'));
  }, [activeCameras]);
  useEffect(() => { localStorage.setItem(STORAGE_KEY_SEARCH, searchQuery); }, [searchQuery]);
  useEffect(() => { localStorage.setItem(STORAGE_KEY_DISTRICT, districtFilter); }, [districtFilter]);
  useEffect(() => { localStorage.setItem(STORAGE_KEY_OFFSET, offset.toString()); }, [offset]);

  const handleCsvImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      setLoading(true); await importCamerasCsv(file); await loadData(true);
      setManageModalOpen(false); toast.success('Cameras imported successfully!');
    } catch (err) { toast.error(`Import failed: ${err.message}`); } 
    finally { setLoading(false); e.target.value = null; }
  };

  const handleClearAll = async () => {
    const ok = await confirmModal({
      title: 'Delete All Cameras',
      message: 'Are you sure you want to delete all cameras? This will remove all feeds and associated detections.',
      confirmText: 'Delete All',
      isDanger: true,
    });
    if (!ok) return;
    try {
      setLoading(true); await deleteAllCameras(); setActiveCameras([]); await loadData(true);
      setManageModalOpen(false); toast.success('All cameras deleted!');
    } catch (err) { toast.error(`Clear failed: ${err.message}`); } 
    finally { setLoading(false); }
  };

  const handleAddCamera = async (cameraData) => {
    try {
      setLoading(true); await addCamera(cameraData); await loadData(true);
      setManageModalOpen(false); toast.success('Camera added successfully!');
    } catch (err) { toast.error(`Failed to add camera: ${err.message}`); } 
    finally { setLoading(false); }
  };

  const handleSingleDelete = async (camera) => {
    const ok = await confirmModal({
      title: 'Delete Camera',
      message: `Are you sure you want to delete Camera #${camera.camera_id} (${camera.name})?`,
      confirmText: 'Delete',
      isDanger: true,
    });
    if (!ok) return;
    try {
      setLoading(true); await deleteSingleCamera(camera.camera_id);
      setActiveCameras(prev => prev.filter(c => c.camera_id !== camera.camera_id));
      await loadData(true); toast.success('Camera deleted successfully!');
    } catch (err) { toast.error(`Delete failed: ${err.message}`); } 
    finally { setLoading(false); }
  };

  const handleSaveEdit = async (cameraId, updatedData) => {
    try {
      setLoading(true); await updateCamera(cameraId, updatedData);
      setActiveCameras(prev => prev.map(c => c.camera_id === cameraId ? { ...c, ...updatedData } : c));
      await loadData(true); setEditingCamera(null); toast.success('Camera updated successfully!');
    } catch (err) { toast.error(`Update failed: ${err.message}`); } 
    finally { setLoading(false); }
  };

  const handleToggleCamera = useCallback((camera) => {
    setActiveCameras(prev => {
      const exists = prev.find(c => c.camera_id === camera.camera_id);
      if (exists) return prev.filter(c => c.camera_id !== camera.camera_id);
      if (camera.status !== 'active') {
        toast.warning('Cannot add an offline or error camera to the video wall.');
        return prev;
      }
      return [...prev, camera];
    });
  }, []);

  const handleRemoveActive = useCallback((cameraId) => {
    setActiveCameras(prev => prev.filter(c => c.camera_id !== cameraId));
  }, []);

  const allGujaratDistricts = [
    'Ahmedabad', 'Amreli', 'Anand', 'Aravalli', 'Banaskantha', 'Bharuch', 
    'Bhavnagar', 'Botad', 'Chhota Udaipur', 'Dahod', 'Dang', 'Devbhoomi Dwarka', 
    'Gandhinagar', 'Gir Somnath', 'Jamnagar', 'Junagadh', 'Kheda', 'Kutch', 
    'Mahisagar', 'Mehsana', 'Morbi', 'Narmada', 'Navsari', 'Panchmahal', 
    'Patan', 'Porbandar', 'Rajkot', 'Sabarkantha', 'Surat', 'Surendranagar', 
    'Tapi', 'Vadodara', 'Valsad'
  ];

  const searchTimeoutRef = useRef(null);
  const searchStringRef = useRef('');

  useEffect(() => {
    if (!filterMenuOpen) return;
    const handleKeyDown = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if (e.key.length !== 1 || e.ctrlKey || e.metaKey || e.altKey) return;
      
      searchStringRef.current += e.key.toLowerCase();
      
      clearTimeout(searchTimeoutRef.current);
      searchTimeoutRef.current = setTimeout(() => {
        searchStringRef.current = '';
      }, 1000);

      const match = allGujaratDistricts.find(d => d.toLowerCase().startsWith(searchStringRef.current));
      if (match) {
        const btn = document.getElementById(`dist-btn-${match}`);
        if (btn) btn.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [filterMenuOpen]);

  const activeCameraIds = useMemo(() => new Set(activeCameras.map(c => c.camera_id)), [activeCameras]);

  const filteredCameras = useMemo(() => {
    return cameras.filter(cam => {
      if (activeCameraIds.has(cam.camera_id)) return false;
      const q = searchQuery.toLowerCase();
      const matchesSearch = !q || String(cam.camera_id).toLowerCase().includes(q) || (cam.name && cam.name.toLowerCase().includes(q));
      if (!matchesSearch) return false;
      if (districtFilter === 'all') return true;
      return cam.district && cam.district.trim() === districtFilter;
    });
  }, [cameras, searchQuery, districtFilter, activeCameraIds]);
  const handleClearWall = () => {
    setActiveCameras([]);
  };

  const handleLoadAllFiltered = () => {
    setActiveCameras(prev => {
      const newActive = [...prev];
      const activeIds = new Set(newActive.map(c => c.camera_id));
      filteredCameras.forEach(cam => {
        if (!activeIds.has(cam.camera_id) && cam.status === 'active') {
          newActive.push(cam);
        }
      });
      return newActive;
    });
  };

  const count = activeCameras.length;
  const cols = count > 0 ? Math.min(4, Math.ceil(Math.sqrt(count))) : 1;
  const rows = count > 0 ? Math.ceil(count / cols) : 1;

  const navbarActions = null;

  return (
    <div className="h-full flex bg-bg-primary overflow-hidden relative">
      <EditCameraModal isOpen={!!editingCamera} camera={editingCamera} onClose={() => setEditingCamera(null)} onSave={handleSaveEdit} isLoading={loading} />
      <CameraManagementModal isOpen={manageModalOpen} onClose={() => setManageModalOpen(false)} onImport={handleCsvImport} onClearAll={handleClearAll} onAddCamera={handleAddCamera} isLoading={loading} />
      {filterMenuOpen && <div className="fixed inset-0 z-40" onClick={() => setFilterMenuOpen(false)} />}
      {navbarActions}

      <div className="w-[260px] flex flex-col bg-bg-elevated border-r border-border-primary shrink-0 relative z-50 shadow-sm">
        <div className="p-3 border-b border-border-secondary shrink-0 relative z-50">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-bold text-text-secondary uppercase tracking-wider truncate mr-2">
              Cameras ({cameras.length}) {loading && <Loader2 className="w-3 h-3 animate-spin inline ml-2 text-accent" />}
            </h2>
            <div className="flex items-center gap-1.5">
              <button onClick={() => { setManageModalOpen(true); setFilterMenuOpen(false); }} className="w-6 h-6 flex items-center justify-center rounded text-text-secondary hover:text-accent hover:bg-bg-hover"><Plus className="w-3.5 h-3.5" /></button>
              <div className="relative">
                <button onClick={() => setFilterMenuOpen(!filterMenuOpen)} className={`w-6 h-6 flex items-center justify-center rounded relative ${filterMenuOpen ? 'text-accent bg-accent/10' : 'text-text-secondary hover:text-accent hover:bg-bg-hover'}`}>
                  <Filter className="w-3.5 h-3.5" />
                  {districtFilter !== 'all' && <span className="absolute top-0.5 right-0.5 w-1.5 h-1.5 rounded-full bg-accent"></span>}
                </button>
                {filterMenuOpen && (
                  <div className="absolute right-0 top-full mt-1 w-48 max-h-64 overflow-y-auto bg-bg-elevated border border-border-secondary rounded-lg shadow-xl py-1 z-50 scrollbar-thin">
                    <button onClick={() => { setDistrictFilter('all'); setFilterMenuOpen(false); }} className={`w-full text-left px-3 py-2 text-sm hover:bg-bg-hover ${districtFilter === 'all' ? 'text-accent font-medium' : 'text-text-primary'}`}>All Districts</button>
                    <div className="h-px bg-border-secondary my-1 mx-2" />
                    {allGujaratDistricts.map(dist => (
                      <button id={`dist-btn-${dist}`} key={dist} onClick={() => { setDistrictFilter(dist); setFilterMenuOpen(false); }} className={`w-full text-left px-3 py-2 text-sm hover:bg-bg-hover ${districtFilter === dist ? 'text-accent font-medium' : 'text-text-primary'}`}>{dist}</button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
          <div className="relative w-full mt-2 flex items-center">
            <input 
              type="text" 
              placeholder="Search cameras..." 
              value={searchQuery} 
              onChange={(e) => setSearchQuery(e.target.value)} 
              className="block w-full pl-3.5 pr-10 py-2.5 border border-transparent rounded-full bg-bg-primary text-text-primary placeholder-text-muted text-sm font-medium focus:outline-none focus:border-accent focus:bg-white focus:ring-1 focus:ring-accent transition-all" 
            />
            {searchQuery && (
              <>
                <div className="absolute right-8 h-4 w-[1px] bg-border-secondary pointer-events-none" />
                <button 
                  type="button" 
                  onClick={() => setSearchQuery('')}
                  className="absolute right-1 w-6 h-6 flex items-center justify-center rounded-full text-text-muted hover:text-text-primary hover:bg-bg-hover"
                >
                  <X className="w-3.5 h-3.5" strokeWidth={2.5} />
                </button>
              </>
            )}
          </div>
          <div className="flex gap-2 mt-3">
            {/* Show Load All if not all filtered cameras are currently active */}
            {filteredCameras.some(cam => !activeCameraIds.has(cam.camera_id)) && (
              <button
                onClick={handleLoadAllFiltered}
                className="flex-1 py-1.5 flex items-center justify-center gap-1.5 bg-accent/10 hover:bg-accent/20 text-accent rounded text-xs font-semibold transition-colors"
              >
                <Layers className="w-3.5 h-3.5" /> Load {districtFilter !== 'all' ? 'District' : 'All'}
              </button>
            )}
            
            {/* Show Remove All if there are any active cameras */}
            {activeCameras.length > 0 && (
              <button
                onClick={handleClearWall}
                className="flex-1 py-1.5 flex items-center justify-center gap-1.5 bg-danger/10 hover:bg-danger/20 text-danger rounded text-xs font-semibold transition-colors"
              >
                <Layers className="w-3.5 h-3.5" /> Remove All
              </button>
            )}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-2 relative">
          {error ? (
            <div className="flex items-center gap-2 text-danger text-sm p-3 bg-danger/10 rounded-md"><AlertCircle className="w-4 h-4 shrink-0" /><span>{error}</span></div>
          ) : cameras.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 text-center"><Navigation className="w-8 h-8 text-text-muted mb-2 opacity-50" /><p className="text-sm text-text-secondary">No cameras found.</p></div>
          ) : (
            <>{filteredCameras.map(cam => (<CameraListCard key={cam.camera_id} camera={cam} isActive={activeCameraIds.has(cam.camera_id)} onToggle={handleToggleCamera} onEdit={() => setEditingCamera(cam)} onDelete={() => handleSingleDelete(cam)} />))}
               {hasMore && <button onClick={loadMore} className="w-full py-2 mt-2 text-sm text-accent hover:bg-accent/10 rounded-md">Load More</button>}
            </>
          )}
        </div>
      </div>

      <div className="flex-1 p-3 overflow-y-auto bg-bg-primary flex flex-col">
        {count === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center border-2 border-dashed border-border-primary rounded-xl m-4 bg-bg-secondary/50 text-center">
            <Layers className="w-12 h-12 text-text-muted mb-4 opacity-50" />
            <h3 className="text-lg font-semibold text-text-secondary mb-1">
              Click a camera to add or<br />use load all to load all the cameras
            </h3>
          </div>
        ) : (
          <div 
            className={`w-full grid gap-2 ${count <= 16 ? 'h-full' : ''}`} 
            style={{ 
              gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, 
              gridTemplateRows: count <= 16 ? `repeat(${rows}, minmax(0, 1fr))` : 'none',
              gridAutoRows: count > 16 ? 'minmax(200px, 25vh)' : 'auto'
            }}
          >
            {activeCameras.map((camera, index) => (<VideoCell key={camera.camera_id} camera={camera} index={index} streamMode={streamMode} onRemove={handleRemoveActive} />))}
          </div>
        )}
      </div>
    </div>
  );
}
