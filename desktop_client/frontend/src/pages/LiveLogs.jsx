import { useState, useEffect } from 'react';
import { fetchAllAlerts, fetchDetections, deleteAllLogs, fetchSystemStatus, connectAlertWebSocket, getApiBase, getApiKey, fetchCameras } from '../services/api';
import { AlertCircle, Activity, Search, RefreshCw, Trash2, PowerOff, Power, X } from 'lucide-react';
import { toast } from '../components/Toast';
import { confirmModal } from '../components/ConfirmModal';

// Formatter for timestamps
const formatTime = (ts) => {
  if (!ts) return 'Unknown';
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
};

const ImageWithFallback = ({ src, onClick }) => {
  const [error, setError] = useState(false);
  
  if (error) {
    return (
      <div className="flex items-center justify-center h-10 w-24 bg-bg-secondary rounded border border-border-primary text-text-muted text-xs cursor-default">
        N/A
      </div>
    );
  }
  
  return (
    <div className="cursor-pointer inline-block" title="Click to open image" onClick={onClick}>
      <img 
        src={src} 
        alt="Detection Crop" 
        className="h-10 min-w-[80px] object-cover rounded border border-border-primary hover:opacity-80 transition-opacity bg-bg-secondary"
        onError={() => setError(true)}
      />
    </div>
  );
};

export default function LiveLogs() {
  const [activeTab, setActiveTab] = useState('detections');
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [workersActive, setWorkersActive] = useState(false);
  const [selectedImage, setSelectedImage] = useState(null);
  const [camerasMap, setCamerasMap] = useState({});

  useEffect(() => {
    fetchCameras().then(cams => {
      const map = {};
      cams.forEach(c => map[c.camera_id] = c.name);
      setCamerasMap(map);
    }).catch(e => console.error("Failed to fetch cameras for names:", e));
  }, []);

  const loadLogs = async (hideLoadingState = false) => {
    if (!hideLoadingState) setLoading(true);
    try {
      if (activeTab === 'alerts') {
        const data = await fetchAllAlerts(200);
        setLogs(data || []);
      } else {
        const data = await fetchDetections(200);
        setLogs(data || []);
      }
    } catch (err) {
      console.error('Failed to load logs:', err);
      setLogs([]);
    } finally {
      if (!hideLoadingState) setLoading(false);
    }
  };

  const handleDeleteAll = async () => {
    const ok = await confirmModal({
      title: 'Clear All Live Logs',
      message: 'Are you sure you want to permanently delete all detection logs? This action cannot be undone.',
      confirmText: 'Clear Logs',
      isDanger: true,
    });
    if (!ok) return;

    setLoading(true);
    try {
      await deleteAllLogs();
      setLogs([]);
      window.dispatchEvent(new CustomEvent('logsCleared'));
      toast.success('All logs cleared successfully!');
    } catch (err) {
      console.error('Failed to delete logs:', err);
      toast.error('Failed to delete logs');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Always load historical logs once on mount/tab change
    loadLogs();
    
    // Use the single WebSocket to receive both live alerts and raw detections instantly
    const ws = connectAlertWebSocket(
      (payload) => {
        setWorkersActive(true);
        // Payload now looks like { type: 'alert' | 'detection', data: {...} }
        if (activeTab === 'alerts' && payload.type === 'alert') {
          setLogs((prev) => [payload.data, ...prev].slice(0, 200));
        } else if (activeTab === 'detections' && payload.type === 'detection') {
          setLogs((prev) => [payload.data, ...prev].slice(0, 200));
        }
      },
      () => setWorkersActive(false),
      () => setWorkersActive(false),
    );
    
    ws.onopen = () => setWorkersActive(true);
    
    // Fallback status check on mount
    fetchSystemStatus()
      .then(status => setWorkersActive(status.workers_active))
      .catch(() => {});
    
    return () => {
      ws.close();
    };
  }, [activeTab]);

  const filteredLogs = logs.filter(log => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    const sourceName = camerasMap[log.camera_id] || `Source #${log.camera_id}`;
    const txt = activeTab === 'alerts' 
      ? `${log.alert_type} ${log.severity} ${log.message} ${sourceName}` 
      : `${log.object_type} ${log.plate_text || ''} ${sourceName}`;
    return txt.toLowerCase().includes(q);
  });

  return (
    <div className="h-full w-full bg-bg-primary flex flex-col p-6 animate-in fade-in">
      <div className="flex items-center justify-between mb-6 shrink-0">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold text-text-bright">System Logs</h2>
            {workersActive ? (
              <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-success/10 border border-success/20 text-success text-xs font-medium">
                <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse"></span>
                LIVE
              </span>
            ) : (
              <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-text-muted/10 border border-text-muted/20 text-text-muted text-xs font-medium">
                <PowerOff className="w-3 h-3" />
                PAUSED (Workers Stopped)
              </span>
            )}
          </div>
          <p className="text-text-secondary text-sm mt-1">Review live alerts and raw detection events across all cameras.</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="w-4 h-4 text-text-muted absolute left-3 top-1/2 -translate-y-1/2" />
            <input 
              type="text"
              placeholder="Search logs..."
              value={searchQuery}
              onChange={(e) => {
                const val = e.target.value.replace(/\s+/g, '').toUpperCase();
                setSearchQuery(val);
              }}
              maxLength={10}
              className="pl-9 pr-8 py-1.5 bg-bg-secondary border border-border-primary rounded-md text-sm text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent w-full"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-text-muted hover:text-text-primary rounded-full hover:bg-bg-hover transition-colors focus:outline-none"
                title="Clear search"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <button 
              onClick={handleDeleteAll}
              disabled={loading}
              className="flex items-center gap-2 px-3 py-1.5 bg-danger/10 border border-danger/20 rounded-md text-danger hover:bg-danger/20 transition-colors text-sm font-medium"
            >
              <Trash2 className="w-4 h-4" />
              Clear Logs
            </button>
            <button 
              onClick={() => loadLogs()}
              disabled={loading}
              className="flex items-center gap-2 px-3 py-1.5 bg-bg-secondary border border-border-primary rounded-md text-text-primary hover:bg-bg-hover transition-colors text-sm font-medium"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </div>
      </div>

      <div className="flex gap-1 mb-4 border-b border-border-primary shrink-0">
        <button
          onClick={() => setActiveTab('detections')}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'detections' ? 'border-accent text-accent' : 'border-transparent text-text-secondary hover:text-text-primary hover:border-border-secondary'}`}
        >
          <Activity className="w-4 h-4" />
          Raw Detections
        </button>
        <button
          onClick={() => setActiveTab('alerts')}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'alerts' ? 'border-accent text-accent' : 'border-transparent text-text-secondary hover:text-text-primary hover:border-border-secondary'}`}
        >
          <AlertCircle className="w-4 h-4" />
          Security Alerts
        </button>
      </div>

      <div className="flex-1 bg-bg-secondary border border-border-primary rounded-lg shadow-sm overflow-hidden flex flex-col">
        <div className="overflow-x-auto flex-1">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-bg-elevated text-text-muted sticky top-0 z-10 border-b border-border-primary">
              {activeTab === 'alerts' ? (
                <tr>
                  <th className="px-4 py-3 font-semibold">Time</th>
                  <th className="px-4 py-3 font-semibold">Type</th>
                  <th className="px-4 py-3 font-semibold">Severity</th>
                  <th className="px-4 py-3 font-semibold">Source</th>
                  <th className="px-4 py-3 font-semibold">Message</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                </tr>
              ) : (
                <tr>
                  <th className="px-4 py-3 font-semibold">Time</th>
                  <th className="px-4 py-3 font-semibold">Image</th>
                  <th className="px-4 py-3 font-semibold">Object</th>
                  <th className="px-4 py-3 font-semibold">Confidence</th>
                  <th className="px-4 py-3 font-semibold">Source</th>
                  <th className="px-4 py-3 font-semibold">Plate Text</th>
                </tr>
              )}
            </thead>
            <tbody className="divide-y divide-border-primary">
              {loading && logs.length === 0 ? (
                <tr>
                  <td colSpan="6" className="px-4 py-8 text-center text-text-muted">Loading logs...</td>
                </tr>
              ) : filteredLogs.length === 0 ? (
                <tr>
                  <td colSpan="6" className="px-4 py-8 text-center text-text-muted">No logs found matching your criteria.</td>
                </tr>
              ) : (
                filteredLogs.map(log => (
                  activeTab === 'alerts' ? (
                    <tr key={log.alert_id} className="hover:bg-bg-hover/50 transition-colors">
                      <td className="px-4 py-2.5 text-text-secondary">{formatTime(log.created_at)}</td>
                      <td className="px-4 py-2.5 font-medium text-text-primary">{log.alert_type}</td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium capitalize ${
                          log.severity === 'high' ? 'bg-danger/10 text-danger border border-danger/20' : 
                          log.severity === 'medium' ? 'bg-warning/10 text-warning border border-warning/20' : 
                          'bg-success/10 text-success border border-success/20'
                        }`}>
                          {log.severity}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-text-primary max-w-[150px] truncate" title={camerasMap[log.camera_id] || `Source #${log.camera_id}`}>
                        {camerasMap[log.camera_id] || `Source #${log.camera_id}`}
                      </td>
                      <td className="px-4 py-2.5 text-text-secondary truncate max-w-xs" title={log.message}>{log.message || '-'}</td>
                      <td className="px-4 py-2.5">
                        {log.acknowledged ? (
                          <span className="text-success text-xs font-medium">Ack'd</span>
                        ) : (
                          <span className="text-warning text-xs font-medium">Open</span>
                        )}
                      </td>
                    </tr>
                  ) : (
                    <tr key={log.detection_id} className="hover:bg-bg-hover/50 transition-colors">
                      <td className="px-4 py-2.5 text-text-secondary">{formatTime(log.detected_at)}</td>
                      <td className="px-4 py-2.5">
                        {log.image_path ? (
                          <ImageWithFallback 
                            src={`${getApiBase()}/crops/${log.image_path.split(/\\|\//).pop()}?api_key=${encodeURIComponent(getApiKey() || "")}`}
                            onClick={() => setSelectedImage(`${getApiBase()}/crops/${log.image_path.split(/\\|\//).pop()}?api_key=${encodeURIComponent(getApiKey() || "")}`)}
                          />
                        ) : (
                          <span className="text-text-muted text-xs">No image</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 font-medium text-text-primary capitalize">{log.object_type}</td>
                      <td className="px-4 py-2.5 text-text-secondary">{(log.confidence * 100).toFixed(1)}%</td>
                      <td className="px-4 py-2.5 text-text-primary max-w-[150px] truncate" title={camerasMap[log.camera_id] || `Source #${log.camera_id}`}>
                        {camerasMap[log.camera_id] || `Source #${log.camera_id}`}
                      </td>
                      <td className="px-4 py-2.5 text-text-bright font-mono">
                        {log.plate_text ? (
                          <div 
                            className="flex items-center gap-2 group cursor-pointer w-max"
                            title="Click to copy number plate"
                            onClick={() => {
                              navigator.clipboard.writeText(log.plate_text).then(() => {
                                // Optional feedback
                              }).catch(err => console.error('Failed to copy', err));
                            }}
                          >
                            <span>{log.plate_text}</span>
                          </div>
                        ) : '-'}
                      </td>
                    </tr>
                  )
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Image Modal */}
      {selectedImage && (
        <div 
          className="fixed inset-0 bg-black/80 z-[10000] flex items-center justify-center p-4"
          onClick={() => setSelectedImage(null)}
        >
          <img 
            src={selectedImage} 
            alt="Full Detection" 
            className="max-w-full max-h-full object-contain rounded border border-border-secondary shadow-2xl"
          />
        </div>
      )}
    </div>
  );
}
