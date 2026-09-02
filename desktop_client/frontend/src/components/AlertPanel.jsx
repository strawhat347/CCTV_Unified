import { useState, useEffect, useRef, useCallback } from 'react';
import { ShieldAlert, CheckCircle2, AlertTriangle, X, Wifi, WifiOff } from 'lucide-react';
import { fetchAlerts, acknowledgeAlert, connectAlertWebSocket, waitForApi } from '../services/api';

const severityStyle = {
  high:   'border-l-danger',
  medium: 'border-l-warning',
  low:    'border-l-info',
};

const severityBadge = {
  high:   'bg-danger/15 text-danger',
  medium: 'bg-warning/15 text-warning',
  low:    'bg-info/15 text-info',
};

function timeAgo(dateStr) {
  const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function AlertPanel({ onClose, onAlertCountChange }) {
  const [alerts, setAlerts] = useState([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const wsRef = useRef(null);

  // Report count to parent
  useEffect(() => {
    if (onAlertCountChange) onAlertCountChange(alerts.length);
  }, [alerts.length, onAlertCountChange]);

  // Fetch initial alerts
  useEffect(() => {
    fetchAlerts(20)
      .then((data) => { setAlerts(data); setError(null); })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  // WebSocket for live alerts
  useEffect(() => {
    let ws = null;
    let isActive = true;

    waitForApi().then(() => {
      if (!isActive) return;
      ws = connectAlertWebSocket(
        (payload) => {
          if (payload.type === 'alert') {
            const newAlert = payload.data;
            setAlerts((prev) => {
              const exists = prev.find((a) => a.alert_id === newAlert.alert_id);
              if (exists) return prev;
              const newList = [newAlert, ...prev].slice(0, 50);
              return newList;
            });
          }
        },
        () => setWsConnected(false),
        () => setWsConnected(false),
      );
      ws.onopen = () => setWsConnected(true);
      wsRef.current = ws;
    });

    return () => { 
      isActive = false;
      if (wsRef.current) wsRef.current.close(); 
    };
  }, []);

  const handleAcknowledge = useCallback(async (alertId) => {
    try {
      await acknowledgeAlert(alertId);
      setAlerts((prev) => prev.filter((a) => a.alert_id !== alertId));
    } catch (err) {
      console.error('Failed to acknowledge alert:', err);
    }
  }, []);

  return (
    <div className="w-80 shrink-0 bg-bg-elevated border-l border-border-primary flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="h-10 px-3 flex items-center justify-between border-b border-border-primary shrink-0">
        <div className="flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-warning" />
          <h2 className="text-base font-semibold text-text-bright">Live Alerts</h2>
          {alerts.length > 0 && (
            <span className="px-1.5 py-0.5 text-xs font-bold bg-danger text-white rounded-full leading-none">{alerts.length}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            {wsConnected ? (
              <><Wifi className="w-3 h-3 text-success" /><span className="text-sm font-medium text-success">Live</span></>
            ) : (
              <><WifiOff className="w-3 h-3 text-text-secondary" /><span className="text-sm font-medium text-text-secondary">Offline</span></>
            )}
          </div>
          <button onClick={onClose} className="p-1 rounded text-text-secondary hover:text-text-bright hover:bg-bg-hover transition-colors">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Alert List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {loading && [1, 2, 3].map((i) => (
          <div key={i} className="h-14 bg-bg-hover rounded animate-pulse" />
        ))}

        {error && (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <AlertTriangle className="w-6 h-6 text-warning mb-2" />
            <p className="text-sm font-medium text-text-secondary">Could not load alerts</p>
            <p className="text-sm font-medium text-text-secondary mt-1">{error}</p>
          </div>
        )}

        {!loading && !error && alerts.length === 0 && (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <CheckCircle2 className="w-6 h-6 text-success mb-2" />
            <p className="text-base font-medium text-text-secondary">All clear — no active alerts</p>
          </div>
        )}

        {alerts.map((alert) => (
          <div
            key={alert.alert_id}
            className={`border-l-2 rounded bg-bg-hover/60 px-3 py-2 flex items-start gap-2.5 transition-colors ${severityStyle[alert.severity] || severityStyle.medium}`}
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5 mb-0.5">
                <span className={`text-xs font-bold uppercase px-1 py-0.5 rounded leading-none ${severityBadge[alert.severity] || severityBadge.medium}`}>
                  {alert.severity}
                </span>
                <span className="text-xs font-semibold text-text-secondary">
                  Cam {alert.camera_id} · {timeAgo(alert.created_at)}
                </span>
              </div>
              <p className="text-sm font-medium text-text-secondary leading-relaxed truncate">
                {alert.message || alert.alert_type.replace(/_/g, ' ')}
              </p>
            </div>
            <button
              onClick={() => handleAcknowledge(alert.alert_id)}
              className="shrink-0 p-1 rounded text-text-secondary hover:text-success hover:bg-success/10 transition-colors"
              title="Acknowledge"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
