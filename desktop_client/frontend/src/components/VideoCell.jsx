import { useState, useEffect, useRef } from 'react';
import Hls from 'hls.js';
import { Video, X, Maximize2, Minimize2, ChevronLeft, RefreshCw, AlertTriangle, Power, Play, Pause, Rewind, FastForward } from 'lucide-react';
import { getStreamUrl, getHlsUrl, releaseStream, toggleCameraScan, fetchSystemStatus, getApiBase, getApiKey } from '../services/api';

/**
 * VideoCell — Individual grid cell in the Fluid Video Wall.
 *
 * Active state: live MJPEG or HLS video stream with overlay controls.
 */
export default function VideoCell({ camera, index = 0, streamMode, onRemove }) {
  const [hasError, setHasError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [hasUserStarted, setHasUserStarted] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [isPlaying, setIsPlaying] = useState(true);
  const [progress, setProgress] = useState(0);
  const isTogglingRef = useRef(false);
  const videoRef = useRef(null);
  const cellRef = useRef(null);

  const handleSeekBg = (e) => {
    if (!videoRef.current || !videoRef.current.duration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const pct = (e.clientX - rect.left) / rect.width;
    videoRef.current.currentTime = pct * videoRef.current.duration;
  };

  const togglePlay = () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
    } else {
      videoRef.current.play().catch(() => {});
    }
  };

  const seek = (seconds) => {
    if (videoRef.current) {
      videoRef.current.currentTime += seconds;
    }
  };

  // Initial fetch and polling for AI worker status
  useEffect(() => {
    const fetchStatus = () => {
      fetchSystemStatus()
        .then(status => {
          if (!isTogglingRef.current) {
            setIsScanning(status.active_cameras?.includes(camera?.camera_id) || false);
          }
        })
        .catch(err => console.error("Failed to fetch system status:", err));
    };
    
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, [camera?.camera_id]);

  const handleToggleScan = async () => {
    if (isTogglingRef.current) return;
    isTogglingRef.current = true;
    
    const newState = !isScanning;
    setIsScanning(newState);
    
    try {
      await toggleCameraScan(camera.camera_id, newState);
    } catch (err) {
      console.error('Failed to toggle scan for camera:', err);
      setIsScanning(!newState); // revert
    } finally {
      // Allow a buffer time for the backend state to update before we accept poll overwrites
      setTimeout(() => {
        isTogglingRef.current = false;
      }, 2000);
    }
  };

  // Stagger the mounting of heavy video feeds to prevent browser lockup
  useEffect(() => {
    const delay = index * 200; // Stagger each camera by 200ms
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
  const isLocalVideo = camera?.stream_url && (camera.stream_url.toLowerCase().endsWith('.mp4') || camera.stream_url.toLowerCase().endsWith('.webm'));
  const effectiveStreamMode = isLocalVideo ? 'mp4' : streamMode;

  useEffect(() => {
    let hls = null;

    if (camera && hasUserStarted && !hasError) {
      if (effectiveStreamMode === 'mp4' && videoRef.current) {
        const filename = camera.stream_url.split(/[/\\]/).pop();
        videoRef.current.src = `${getApiBase()}/videos/${filename}?api_key=${encodeURIComponent(getApiKey() || "")}`;
        videoRef.current.play().catch(() => {});
      } else if (effectiveStreamMode === 'hls') {
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
  }, [camera, effectiveStreamMode, hasError, retryKey, hasUserStarted]);

  // ── Release stream on unmount / camera change ─────────
  useEffect(() => {
    return () => {
      if (camera) {
        releaseStream(camera.camera_id);
      }
      // Force-close MJPEG/video connections by clearing the src attribute.
      // Browsers (especially Chromium) keep HTTP sockets open for <img> MJPEG
      // streams even after the DOM node is removed, causing socket exhaustion.
      if (videoRef.current) {
        videoRef.current.pause();
        videoRef.current.removeAttribute('src');
        videoRef.current.load();
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
        !hasUserStarted ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-bg-elevated cursor-pointer hover:bg-bg-hover transition-colors group/play" onClick={() => setHasUserStarted(true)}>
             <div className="w-16 h-16 rounded-full bg-accent/80 flex items-center justify-center group-hover/play:bg-accent transition-colors shadow-lg">
                <Play className="w-8 h-8 text-white ml-1" />
             </div>
             <p className="mt-4 font-semibold text-sm text-text-primary">{camera.name || `Camera ${camera.camera_id}`}</p>
             <p className="text-xs text-text-muted">Click to Start Stream</p>
          </div>
        ) : effectiveStreamMode === 'mjpeg' || effectiveStreamMode === 'unknown' ? (
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
            className="w-full h-full object-contain bg-black cursor-default animate-in fade-in duration-300"
            muted={true}
            playsInline
            controls={false}
            onPlay={() => setIsPlaying(true)}
            onPause={() => {
              setIsPlaying(false);
              if (isScanning) handleToggleScan();
            }}
            onTimeUpdate={() => {
              if (videoRef.current && videoRef.current.duration) {
                setProgress(videoRef.current.currentTime / videoRef.current.duration);
              }
            }}
            onEnded={() => {
              if (videoRef.current) {
                videoRef.current.pause();
              }
              if (isScanning) {
                handleToggleScan();
              }
            }}
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

      {/* Unified YouTube-Style Bottom Bar */}
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent pt-8 pb-2 px-3 z-50 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col gap-1">
        
        {/* Progress Bar (Scrubber) */}
        {isLocalVideo && (
          <div 
            className="w-full h-1.5 bg-white/30 rounded cursor-pointer mb-1 relative overflow-hidden"
            onClick={handleSeekBg}
          >
            <div 
              className="absolute top-0 left-0 bottom-0 bg-accent transition-all duration-75"
              style={{ width: `${progress * 100}%` }}
            />
          </div>
        )}

        {/* Bottom Row */}
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center gap-3 overflow-hidden">
            
            {/* Media Controls */}
            {isLocalVideo && (
              <div className="flex items-center gap-2 shrink-0">
                <button onClick={() => seek(-10)} className="text-white hover:text-accent transition-colors"><Rewind className="w-4 h-4" /></button>
                <button onClick={togglePlay} className="text-white hover:text-accent transition-colors">
                  {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5" />}
                </button>
                <button onClick={() => seek(10)} className="text-white hover:text-accent transition-colors"><FastForward className="w-4 h-4" /></button>
              </div>
            )}

            {/* Camera Info */}
            <div className="flex flex-col text-white min-w-0">
              <span className="font-medium text-xs truncate">{camera.name || `Camera ${camera.camera_id}`}</span>
              {camera.department && (
                <span className="text-[10px] text-gray-300 truncate">{camera.department}</span>
              )}
            </div>
          </div>
          
          {/* Status Dot */}
          <div className={`w-2 h-2 rounded-full ${statusColor} shrink-0 ml-2 shadow-[0_0_8px_rgba(0,0,0,0.5)]`} title={camera.status} />
        </div>
      </div>
    </div>
  );
}
