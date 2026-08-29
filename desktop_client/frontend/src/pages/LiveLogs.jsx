import { useState, useEffect } from 'react';
import { fetchAllAlerts, fetchDetections } from '../services/api';
import { AlertCircle, Activity, Search, RefreshCw } from 'lucide-react';

// Formatter for timestamps
const formatTime = (ts) => {
  if (!ts) return 'Unknown';
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
};

export default function LiveLogs() {
  const [activeTab, setActiveTab] = useState('alerts');
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  const loadLogs = async () => {
    setLoading(true);
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
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, [activeTab]);

  const filteredLogs = logs.filter(log => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    const txt = activeTab === 'alerts' 
      ? `${log.alert_type} ${log.severity} ${log.message} ${log.camera_id}` 
      : `${log.object_type} ${log.plate_text || ''} ${log.camera_id}`;
    return txt.toLowerCase().includes(q);
  });

  return (
    <div className="h-full w-full bg-bg-primary flex flex-col p-6 animate-in fade-in">
      <div className="flex items-center justify-between mb-6 shrink-0">
        <div>
          <h2 className="text-2xl font-bold text-text-bright">System Logs</h2>
          <p className="text-text-secondary text-sm mt-1">Review live alerts and raw detection events across all cameras.</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="w-4 h-4 text-text-muted absolute left-3 top-1/2 -translate-y-1/2" />
            <input 
              type="text"
              placeholder="Search logs..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 pr-4 py-1.5 bg-bg-secondary border border-border-primary rounded-md text-sm text-text-primary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
            />
          </div>
          <button 
            onClick={loadLogs}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 bg-bg-secondary border border-border-primary rounded-md text-text-primary hover:bg-bg-hover transition-colors text-sm font-medium"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      <div className="flex gap-1 mb-4 border-b border-border-primary shrink-0">
        <button
          onClick={() => setActiveTab('alerts')}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'alerts' ? 'border-accent text-accent' : 'border-transparent text-text-secondary hover:text-text-primary hover:border-border-secondary'}`}
        >
          <AlertCircle className="w-4 h-4" />
          Security Alerts
        </button>
        <button
          onClick={() => setActiveTab('detections')}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'detections' ? 'border-accent text-accent' : 'border-transparent text-text-secondary hover:text-text-primary hover:border-border-secondary'}`}
        >
          <Activity className="w-4 h-4" />
          Raw Detections
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
                  <th className="px-4 py-3 font-semibold">Camera ID</th>
                  <th className="px-4 py-3 font-semibold">Message</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                </tr>
              ) : (
                <tr>
                  <th className="px-4 py-3 font-semibold">Time</th>
                  <th className="px-4 py-3 font-semibold">Object</th>
                  <th className="px-4 py-3 font-semibold">Confidence</th>
                  <th className="px-4 py-3 font-semibold">Camera ID</th>
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
                      <td className="px-4 py-2.5 text-text-primary">Cam #{log.camera_id}</td>
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
                      <td className="px-4 py-2.5 font-medium text-text-primary capitalize">{log.object_type}</td>
                      <td className="px-4 py-2.5 text-text-secondary">{(log.confidence * 100).toFixed(1)}%</td>
                      <td className="px-4 py-2.5 text-text-primary">Cam #{log.camera_id}</td>
                      <td className="px-4 py-2.5 text-text-bright font-mono">{log.plate_text || '-'}</td>
                    </tr>
                  )
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
