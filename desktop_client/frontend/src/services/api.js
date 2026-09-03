/**
 * Helper to get the API base URL.
 * Reads API_BASE_URL and API_KEY injected by PyWebView, with dev fallbacks.
 */

export const getApiBase = () => window.API_BASE_URL || 'https://localhost:8002';

export const getApiKey = () => window.API_KEY || (import.meta.env.DEV ? 'O-LYst-neW08fjz-b0jkn6dIf8kN3OprsnBxruSHpF4' : 'O-LYst-neW08fjz-b0jkn6dIf8kN3OprsnBxruSHpF4');
const getHeaders = () => ({ 'X-API-Key': getApiKey() || '', 'Content-Type': 'application/json' });

export async function waitForApi() {
  if (getApiKey()) return;
  
  // If we are in PyWebView, we wait for the python api to become available
  return new Promise((resolve) => {
    const checkApi = async () => {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.get_config) {
        try {
          const config = await window.pywebview.api.get_config();
          window.API_KEY = config.API_KEY;
          window.API_BASE_URL = config.API_BASE_URL;
          window.USE_EXTERNAL_CDN = config.USE_EXTERNAL_CDN;
          resolve();
        } catch (e) {
          console.error("Failed to get config from python", e);
          setTimeout(checkApi, 50);
        }
      } else {
        setTimeout(checkApi, 50);
      }
    };
    checkApi();
  });
}

// ── Cameras ──────────────────────────────────────────────
export async function fetchCameras(status, q, limit = 100, offset = 0) {
  await waitForApi();
  const url = new URL(`${getApiBase()}/cameras`);
  if (status) url.searchParams.set('status', status);
  if (q) url.searchParams.set('q', q);
  url.searchParams.set('limit', limit);
  url.searchParams.set('offset', offset);
  
  const res = await fetch(url, { headers: getHeaders() });
  if (!res.ok) throw new Error(`GET /cameras failed: ${res.status}`);
  return res.json();
}

export async function fetchCamera(cameraId) {
  await waitForApi();
  const res = await fetch(`${getApiBase()}/cameras/${cameraId}`, { headers: getHeaders() });
  if (!res.ok) throw new Error(`GET /cameras/${cameraId} failed: ${res.status}`);
  return res.json();
}

export async function addCamera(cameraData) {
  await waitForApi();
  const res = await fetch(`${getApiBase()}/cameras`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(cameraData)
  });
  if (!res.ok) throw new Error(`POST /cameras failed: ${res.status}`);
  return res.json();
}

export async function deleteAllCameras() {
  await waitForApi();
  const res = await fetch(`${getApiBase()}/cameras?confirm=DELETE_ALL_CAMERAS`, {
    method: 'DELETE',
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error(`DELETE /cameras failed: ${res.status}`);
  return res.json();
}

export async function deleteSingleCamera(cameraId) {
  await waitForApi();
  const res = await fetch(`${getApiBase()}/cameras/${cameraId}`, {
    method: 'DELETE',
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error(`DELETE /cameras/${cameraId} failed: ${res.status}`);
  return res.json();
}

export async function updateCamera(cameraId, cameraData) {
  await waitForApi();
  const res = await fetch(`${getApiBase()}/cameras/${cameraId}`, {
    method: 'PUT',
    headers: getHeaders(),
    body: JSON.stringify(cameraData)
  });
  if (!res.ok) throw new Error(`PUT /cameras/${cameraId} failed: ${res.status}`);
  return res.json();
}

export async function importCamerasCsv(file) {
  await waitForApi();
  const formData = new FormData();
  formData.append('file', file);
  
  // Create a copy of headers without Content-Type because fetch 
  // automatically sets Content-Type to multipart/form-data with boundary when passing FormData
  const uploadHeaders = { ...getHeaders() };
  delete uploadHeaders['Content-Type'];

  const res = await fetch(`${getApiBase()}/cameras/bulk`, {
    method: 'POST',
    headers: uploadHeaders,
    body: formData,
  });
  if (!res.ok) throw new Error(`POST /cameras/bulk failed: ${res.status}`);
  return res.json();
}

// ── Detections ───────────────────────────────────────────
export async function fetchDetections(limit = 100) {
  await waitForApi();
  const res = await fetch(`${getApiBase()}/detections?limit=${limit}`, { headers: getHeaders() });
  if (!res.ok) throw new Error(`GET /detections failed: ${res.status}`);
  return res.json();
}

export async function fetchDetectionsByCamera(cameraId, limit = 100) {
  await waitForApi();
  const res = await fetch(`${getApiBase()}/detections/by-camera/${cameraId}?limit=${limit}`, { headers: getHeaders() });
  if (!res.ok) throw new Error(`GET /detections/by-camera/${cameraId} failed: ${res.status}`);
  return res.json();
}

// ── Alerts ───────────────────────────────────────────────
export async function fetchAlerts(limit = 50) {
  await waitForApi();
  const res = await fetch(`${getApiBase()}/alerts/?limit=${limit}`, { headers: getHeaders() });
  if (!res.ok) throw new Error(`GET /alerts failed: ${res.status}`);
  return res.json();
}

export async function fetchAllAlerts(limit = 200) {
  await waitForApi();
  const res = await fetch(`${getApiBase()}/alerts/all?limit=${limit}`, { headers: getHeaders() });
  if (!res.ok) throw new Error(`GET /alerts/all failed: ${res.status}`);
  return res.json();
}

export async function acknowledgeAlert(alertId) {
  await waitForApi();
  const res = await fetch(`${getApiBase()}/alerts/${alertId}/acknowledge`, {
    method: 'POST',
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error(`POST /alerts/${alertId}/acknowledge failed: ${res.status}`);
  return res.json();
}

// ── WebSocket (live alerts) ──────────────────────────────
export function connectAlertWebSocket(onMessage, onError, onClose) {
  const wsBase = getApiBase().replace(/^http/, 'ws');
  const ws = new WebSocket(`${wsBase}/alerts/ws?api_key=${getApiKey() || ""}`);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (e) {
      console.error('WS parse error:', e);
    }
  };

  ws.onerror = (event) => {
    console.error('WS error:', event);
    if (onError) onError(event);
  };

  ws.onclose = (event) => {
    console.log('WS closed:', event.code);
    if (onClose) onClose(event);
  };

  return ws;
}

// ── Streams (Video Wall) ─────────────────────────────────
/**
 * Get the stream URL for a camera.
 */
export function getStreamUrl(cameraId) {
  if (window.USE_EXTERNAL_CDN) {
    return `https://live.corp8.cloud/stream/${cameraId}`;
  }
  return `${getApiBase()}/streams/${cameraId}/mjpeg?api_key=${encodeURIComponent(getApiKey() || "")}`;
}

/**
 * Get the HLS playlist URL for a camera.
 */
export function getHlsUrl(cameraId) {
  if (window.USE_EXTERNAL_CDN) {
    return `https://live.corp8.cloud/live/stream/${cameraId}/index.m3u8`;
  }
  return `${getApiBase()}/streams/${cameraId}/hls/stream.m3u8?api_key=${encodeURIComponent(getApiKey() || "")}`;
}

/**
 * Get a single JPEG snapshot for a camera (thumbnails).
 */
export function getSnapshotUrl(cameraId) {
  return `${getApiBase()}/streams/${cameraId}/snapshot?api_key=${encodeURIComponent(getApiKey() || "")}`;
}

/**
 * Fetch the active streaming mode (hls or mjpeg).
 */
export async function fetchStreamMode() {
  await waitForApi();
  if (window.USE_EXTERNAL_CDN) {
    return { mode: 'mp4' };
  }
  try {
    const res = await fetch(`${getApiBase()}/streams/mode`, { headers: getHeaders() });
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.error("Failed to fetch stream mode", e);
  }
  return { mode: 'mjpeg' };
}

/**
 * Release a viewer slot for a camera stream.
 * Call when a VideoCell unmounts or camera is removed from a cell.
 */
export async function releaseStream(cameraId) {
  await waitForApi();
  try {
    await fetch(`${getApiBase()}/streams/${cameraId}/hls/release?api_key=${encodeURIComponent(getApiKey() || "")}`);
  } catch {
    // Best-effort release — don't throw if the backend is unreachable
  }
}



/**
 * Temporary function to wipe all alerts and detections from the database.
 */
export async function deleteAllLogs() {
  await waitForApi();
  const res = await fetch(`${getApiBase()}/detections?confirm=DELETE_ALL_LOGS`, {
    method: 'DELETE',
    headers: getHeaders()
  });
  if (!res.ok) throw new Error('Failed to delete logs');
  return res.json();
}

/**
 * Check if the backend pipeline workers are actively running.
 */
export async function fetchSystemStatus() {
  await waitForApi();
  const res = await fetch(`${getApiBase()}/system/status`, { headers: getHeaders() });
  if (!res.ok) throw new Error(`GET /system/status failed: ${res.status}`);
  return res.json();
}

/**
 * Start or stop backend scanning workers.
 */
export async function toggleScan(scanning) {
  await waitForApi();
  const res = await fetch(`${getApiBase()}/system/scan`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ scanning }),
  });
  if (!res.ok) throw new Error(`POST /system/scan failed: ${res.status}`);
  return res.json();
}

/**
 * Start or stop the backend scanning worker for a specific camera.
 */
export async function toggleCameraScan(cameraId, scanning) {
  await waitForApi();
  const res = await fetch(`${getApiBase()}/system/scan/${cameraId}`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ scanning }),
  });
  if (!res.ok) throw new Error(`POST /system/scan/${cameraId} failed: ${res.status}`);
  return res.json();
}

/**
 * Start or stop the backend scanning worker for a specific offline video file.
 */
export async function toggleVideoScan(videoId, scanning) {
  await waitForApi();
  const res = await fetch(`${getApiBase()}/system/scan/video/${videoId}`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ scanning }),
  });
  if (!res.ok) throw new Error(`POST /system/scan/video/${videoId} failed: ${res.status}`);
  return res.json();
}


