import { useState, useEffect, useRef } from 'react';
import Hls from 'hls.js';
import { Video, X, Maximize2, Minimize2, ChevronLeft, RefreshCw, AlertTriangle } from 'lucide-react';
import { getStreamUrl, getHlsUrl, getSnapshotUrl, releaseStream } from '../services/api';

/**
 * VideoCell — Individual grid cell in the Fluid Video Wall.
 *
 * Active state: live MJPEG or HLS video stream with overlay controls.
 */
export default function VideoCell({ camera, index = 0, streamMode, onRemove }) {
  const [hasError, setHasError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [shouldLoad, setShouldLoad] = useState(false);
  const videoRef = useRef(null);
  const cellRef = useRef(null);

  // Stagger the mounting of heavy video feeds to prevent browser lockup
  useEffect(() => {
    const delay = index * 150; // Stagger each camera by 150ms
    const timer = setTimeout(() => setShouldLoad(true), delay);
    return () => clearTimeout(timer);
  }, [index]);

  // Track fullscreen changes
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === cellRef.current);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  // ── Fullscreen ────────────────────────────────────────
  const toggleFullscreen = () => {
    if (cellRef.current) {
      if (!document.fullscreenElement) {
        cellRef.current.requestFullscreen().catch(() => {});
      } else {
        document.exitFullscreen();
      }
    }
  };

  // ── Retry ─────────────────────────────────────────────
  const handleRetry = () => {
    setHasError(false);
    setRetryKey(prev => prev + 1);
  };

  // ── HLS setup & teardown ──────────────────────────────
  useEffect(() => {
    let hls = null;

    if (camera && shouldLoad && !hasError) {
      if (streamMode === 'mp4' && videoRef.current) {
        videoRef.current.src = getStreamUrl(camera.camera_id);
        videoRef.current.play().catch(() => {});
      } else if (streamMode === 'hls') {
        const hlsUrl = getHlsUrl(camera.camera_id);

        if (Hls.isSupported() && videoRef.current) {
          hls = new Hls({
            liveDurationInfinity: true,
            enableWorker: true,
            lowLatencyMode: true,
          });

          hls.loadSource(hlsUrl);
          hls.attachMedia(videoRef.current);

          hls.on(Hls.Events.MANIFEST_PARSED, () => {
            videoRef.current?.play().catch(() => {});
          });

          hls.on(Hls.Events.ERROR, (_event, data) => {
            if (data.fatal) {
              switch (data.type) {
                case Hls.ErrorTypes.NETWORK_ERROR:
                  hls.startLoad();
                  break;
                case Hls.ErrorTypes.MEDIA_ERROR:
                  hls.recoverMediaError();
                  break;
                default:
                  setHasError(true);
                  hls.destroy();
                  break;
              }
            }
          });
        } else if (videoRef.current?.canPlayType('application/vnd.apple.mpegurl')) {
          videoRef.current.src = hlsUrl;
          videoRef.current.play().catch(() => {});
        }
      }
    }

    return () => {
      if (hls) hls.destroy();
    };
  }, [camera, streamMode, hasError, retryKey, shouldLoad]);

  // ── Release stream on unmount / camera change ─────────
  useEffect(() => {
    return () => {
      if (camera) {
        releaseStream(camera.camera_id);
      }
    };
  }, [camera]);

  // Reset error state when camera changes
  useEffect(() => {
    setHasError(false);
    setRetryKey(0);
  }, [camera?.camera_id]);

  if (!camera) return null;

  const statusColor =
    camera.status === 'active'   ? 'bg-success' :
    camera.status === 'error'    ? 'bg-danger'  :
    camera.status === 'inactive' ? 'bg-text-muted' : 'bg-warning';

  return (
    <div
      ref={cellRef}
      className={`relative group w-full h-full bg-black overflow-hidden transition-all duration-200 border-border-primary
        ${isFullscreen ? 'rounded-none border-none' : 'rounded-lg border'}`}
      onDoubleClick={toggleFullscreen}
    >
      {/* Stream or Error */}
      {!hasError ? (
        !shouldLoad ? (
          <img
            key={`snapshot-${camera.camera_id}`}
            src={getSnapshotUrl(camera.camera_id)}
            alt={camera.name || `Camera ${camera.camera_id}`}
            className="w-full h-full object-cover cursor-default opacity-50 transition-opacity duration-300"
          />
        ) : streamMode === 'mjpeg' || streamMode === 'unknown' ? (
          <img
            key={`mjpeg-${camera.camera_id}-${retryKey}`}
            src={getStreamUrl(camera.camera_id)}
            alt={camera.name || `Camera ${camera.camera_id}`}
            className="w-full h-full object-cover cursor-default animate-in fade-in duration-300"
            onError={() => setHasError(true)}
          />
        ) : (
          <video
            ref={videoRef}
            className="w-full h-full object-cover cursor-default animate-in fade-in duration-300"
            muted
            playsInline
            autoPlay
            poster={getSnapshotUrl(camera.camera_id)}
          />
        )
      ) : (
        /* Error overlay */
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-bg-elevated">
          <AlertTriangle className="w-8 h-8 text-warning mb-2" />
          <p className="font-semibold text-sm text-text-primary">{camera.name || `Camera ${camera.camera_id}`}</p>
          <p className="text-xs text-text-muted mb-3">Stream Unavailable</p>
          <button
            onClick={handleRetry}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-accent text-white rounded-md text-xs font-medium hover:bg-accent-hover transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Retry
          </button>
        </div>
      )}

      {/* Camera ID (Top Left) */}
      <div className="absolute top-1.5 left-1.5 z-10 px-1.5 py-0.5 bg-black/50 rounded backdrop-blur-sm pointer-events-none">
        <span className="text-green-400 font-bold text-xs tracking-wider">#{camera.camera_id}</span>
      </div>

      {/* Hover controls (top-right) */}
      <div className="absolute top-1.5 right-1.5 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity z-10">
        {isFullscreen && (
          <button
            onClick={() => alert('Vehicle bounding system: To be implemented.')}
            className="p-1 bg-accent/80 hover:bg-accent text-white rounded backdrop-blur-sm transition-colors"
            title="Toggle Vehicle Bounding System"
          >
            <Video className="w-3.5 h-3.5" />
          </button>
        )}
        <button
          onClick={toggleFullscreen}
          className="p-1 bg-black/50 hover:bg-black/70 text-white rounded backdrop-blur-sm transition-colors"
          title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
        >
          {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
        </button>
        {isFullscreen ? (
          <button
            onClick={() => document.exitFullscreen()}
            className="p-1 bg-black/50 hover:bg-black/70 text-white rounded backdrop-blur-sm transition-colors"
            title="Go Back"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
        ) : (
          <button
            onClick={() => onRemove(camera.camera_id)}
            className="p-1 bg-danger/80 hover:bg-danger text-white rounded backdrop-blur-sm transition-colors"
            title="Remove camera"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* Bottom info bar */}
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-2 pt-6 flex items-end justify-between z-10 opacity-0 group-hover:opacity-100 transition-opacity">
        <div className="flex flex-col text-white min-w-0">
          <span className="font-medium text-xs truncate">{camera.name || `Camera ${camera.camera_id}`}</span>
          {camera.department && (
            <span className="text-[10px] text-gray-300 truncate">{camera.department}</span>
          )}
        </div>
        <div className={`w-2 h-2 rounded-full ${statusColor} shrink-0`} title={camera.status} />
      </div>
    </div>
  );
}
