/**
 * Helper to get the API base URL.
 * Reads API_BASE_URL injected by PyWebView, with dev fallbacks.
 * 
 * Step 11: Auth is now JWT-based. The API_KEY is only used for
 * internal pipeline endpoints. The frontend uses Bearer tokens.
 */

export const getApiBase = () => window.API_BASE_URL || 'https://localhost:8002';

// ── Auth Token Management ────────────────────────────────
// Store JWT tokens in localStorage so sessions survive page reloads
export function getAccessToken() { return localStorage.getItem('access_token'); }

export function getCurrentUser() {
  const token = getAccessToken();
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return { username: payload.sub, role: payload.role };
  } catch (e) {
    return null;
  }
}
export function getRefreshToken() { return localStorage.getItem('refresh_token'); }
export function setTokens(access, refresh) {
  if (access) localStorage.setItem('access_token', access);
  if (refresh) localStorage.setItem('refresh_token', refresh);
}
export function clearTokens() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
}
export function logout() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
}

export function isLoggedIn() { return !!getAccessToken(); }

// Legacy API key support (still needed for stream URLs in <img>/<video> src)
export const getApiKey = () => window.API_KEY || (import.meta.env.DEV ? 'O-LYst-neW08fjz-b0jkn6dIf8kN3OprsnBxruSHpF4' : 'O-LYst-neW08fjz-b0jkn6dIf8kN3OprsnBxruSHpF4');

const getHeaders = () => {
  const headers = { 'Content-Type': 'application/json' };
  if (getAccessToken()) {
    headers['Authorization'] = `Bearer ${getAccessToken()}`;
  }
  // Always include X-API-Key as fallback for endpoints that support it
  const apiKey = getApiKey();
  if (apiKey) {
    headers['X-API-Key'] = apiKey;
  }
  return headers;
};

export async function waitForApi() {
  if (getAccessToken()) return; // Already logged in via JWT
  if (getApiKey()) return;  // Legacy API key mode
  
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

// ── Auth API Calls ───────────────────────────────────────

/**
 * Login with username/password. Returns { access_token, refresh_token, token_type }.
 */
export async function login(username, password) {
  const formData = new URLSearchParams();
  formData.append('username', username);
  formData.append('password', password);
  
  const res = await fetch(`${getApiBase()}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Login failed' }));
    throw new Error(err.detail || `Login failed: ${res.status}`);
  }
  const data = await res.json();
  setTokens(data.access_token, data.refresh_token);
  return data;
}

/**
 * Refresh the access token using the stored refresh token.
 */
export async function refreshAccessToken() {
  if (!getRefreshToken()) throw new Error('No refresh token available');
  
  const res = await fetch(`${getApiBase()}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: getRefreshToken() }),
  });
  if (!res.ok) {
    clearTokens();
    throw new Error('Session expired — please log in again');
  }
  const data = await res.json();
  setTokens(data.access_token);
  return data;
}

/**
 * Fetch wrapper that auto-refreshes expired access tokens.
 */
async function authFetch(url, options = {}) {
  await waitForApi();
  
  const defaultHeaders = getHeaders();
  if (options.body instanceof FormData) {
    delete defaultHeaders['Content-Type'];
  }
  
  options.headers = { ...defaultHeaders, ...options.headers };
  
  let res = await fetch(url, options);
  
  // If 401 and we have a refresh token, try refreshing once
  if (res.status === 401 && getRefreshToken()) {
    try {
      await refreshAccessToken();
      options.headers = { ...getHeaders(), ...options.headers };
      res = await fetch(url, options);
    } catch {
      // Refresh failed — propagate the 401
    }
  }
  
  return res;
}

/**
 * Get current user info.
 */
export async function fetchCurrentUser() {
  const res = await authFetch(`${getApiBase()}/auth/me`);
  if (!res.ok) throw new Error(`GET /auth/me failed: ${res.status}`);
  return res.json();
}

// ── Cameras ──────────────────────────────────────────────
export async function fetchCameras(status, q, limit = 100, offset = 0) {
  const url = new URL(`${getApiBase()}/cameras`);
  if (status) url.searchParams.set('status', status);
  if (q) url.searchParams.set('q', q);
  url.searchParams.set('limit', limit);
  url.searchParams.set('offset', offset);
  
  const res = await authFetch(url);
  if (!res.ok) throw new Error(`GET /cameras failed: ${res.status}`);
  return res.json();
}

export async function fetchCamera(cameraId) {
  const res = await authFetch(`${getApiBase()}/cameras/${cameraId}`);
  if (!res.ok) throw new Error(`GET /cameras/${cameraId} failed: ${res.status}`);
  return res.json();
}

export async function addCamera(cameraData) {
  const res = await authFetch(`${getApiBase()}/cameras`, {
    method: 'POST',
    body: JSON.stringify(cameraData)
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    let errMsg = `POST /cameras failed: ${res.status}`;
    if (errorData.detail) {
      errMsg = Array.isArray(errorData.detail) 
        ? errorData.detail.map(d => d.msg).join(', ') 
        : errorData.detail;
    }
    throw new Error(errMsg);
  }
  return res.json();
}

export async function deleteAllCameras() {
  const res = await authFetch(`${getApiBase()}/cameras?confirm=DELETE_ALL_CAMERAS`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`DELETE /cameras failed: ${res.status}`);
  return res.json();
}

export async function deleteSingleCamera(cameraId) {
  const res = await authFetch(`${getApiBase()}/cameras/${cameraId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`DELETE /cameras/${cameraId} failed: ${res.status}`);
  return res.json();
}

export async function updateCamera(cameraId, cameraData) {
  const res = await authFetch(`${getApiBase()}/cameras/${cameraId}`, {
    method: 'PUT',
    body: JSON.stringify(cameraData)
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    let errMsg = `PUT /cameras/${cameraId} failed: ${res.status}`;
    if (errorData.detail) {
      errMsg = Array.isArray(errorData.detail) 
        ? errorData.detail.map(d => d.msg).join(', ') 
        : errorData.detail;
    }
    throw new Error(errMsg);
  }
  return res.json();
}

export async function importCamerasCsv(file) {
  const formData = new FormData();
  formData.append('file', file);
  
  // Create headers without Content-Type because fetch 
  // automatically sets Content-Type to multipart/form-data with boundary when passing FormData
  const uploadHeaders = { ...getHeaders() };
  delete uploadHeaders['Content-Type'];

  const res = await authFetch(`${getApiBase()}/cameras/bulk`, {
    method: 'POST',
    headers: uploadHeaders,
    body: formData,
  });
  if (!res.ok) throw new Error(`POST /cameras/bulk failed: ${res.status}`);
  return res.json();
}

// ── Detections ───────────────────────────────────────────
export async function fetchDetections(limit = 100) {
  const res = await authFetch(`${getApiBase()}/detections?limit=${limit}`);
  if (!res.ok) throw new Error(`GET /detections failed: ${res.status}`);
  return res.json();
}

export async function fetchDetectionsByCamera(cameraId, limit = 100) {
  const res = await authFetch(`${getApiBase()}/detections/by-camera/${cameraId}?limit=${limit}`);
  if (!res.ok) throw new Error(`GET /detections/by-camera/${cameraId} failed: ${res.status}`);
  return res.json();
}

// ── Alerts ───────────────────────────────────────────────
export async function fetchAlerts(limit = 50) {
  const res = await authFetch(`${getApiBase()}/alerts/?limit=${limit}`);
  if (!res.ok) throw new Error(`GET /alerts failed: ${res.status}`);
  return res.json();
}

export async function fetchAllAlerts(limit = 200) {
  const res = await authFetch(`${getApiBase()}/alerts/all?limit=${limit}`);
  if (!res.ok) throw new Error(`GET /alerts/all failed: ${res.status}`);
  return res.json();
}

export async function acknowledgeAlert(alertId) {
  const res = await authFetch(`${getApiBase()}/alerts/${alertId}/acknowledge`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`POST /alerts/${alertId}/acknowledge failed: ${res.status}`);
  return res.json();
}

// ── WebSocket (live alerts) ──────────────────────────────
export function connectAlertWebSocket(onMessage, onError, onClose) {
  const wsBase = getApiBase().replace(/^http/, 'ws');
  // Use JWT token for WebSocket auth (preferred), fall back to API key
  const authParam = getAccessToken() 
    ? `token=${encodeURIComponent(getAccessToken())}`
    : `api_key=${encodeURIComponent(getApiKey() || "")}`;
  const ws = new WebSocket(`${wsBase}/alerts/ws?${authParam}`);

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
 * Uses JWT token for auth when available, falls back to API key.
 */
export function getStreamUrl(cameraId) {
  if (window.USE_EXTERNAL_CDN) {
    return `https://live.corp8.cloud/stream/${cameraId}`;
  }
  const authParam = getAccessToken()
    ? `token=${encodeURIComponent(getAccessToken())}`
    : `api_key=${encodeURIComponent(getApiKey() || "")}`;
  return `${getApiBase()}/streams/${cameraId}/mjpeg?${authParam}`;
}

/**
 * Get the HLS playlist URL for a camera.
 */
export function getHlsUrl(cameraId) {
  if (window.USE_EXTERNAL_CDN) {
    return `https://live.corp8.cloud/live/stream/${cameraId}/index.m3u8`;
  }
  const authParam = getAccessToken()
    ? `token=${encodeURIComponent(getAccessToken())}`
    : `api_key=${encodeURIComponent(getApiKey() || "")}`;
  return `${getApiBase()}/streams/${cameraId}/hls/stream.m3u8?${authParam}`;
}

/**
 * Get a single JPEG snapshot for a camera (thumbnails).
 */
export function getSnapshotUrl(cameraId) {
  const authParam = getAccessToken()
    ? `token=${encodeURIComponent(getAccessToken())}`
    : `api_key=${encodeURIComponent(getApiKey() || "")}`;
  return `${getApiBase()}/streams/${cameraId}/snapshot?${authParam}`;
}

/**
 * Fetch the active streaming mode (hls or mjpeg).
 */
export async function fetchStreamMode() {
  if (window.USE_EXTERNAL_CDN) {
    return { mode: 'mp4' };
  }
  try {
    const res = await authFetch(`${getApiBase()}/streams/mode`);
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
  try {
    const authParam = getAccessToken()
      ? `token=${encodeURIComponent(getAccessToken())}`
      : `api_key=${encodeURIComponent(getApiKey() || "")}`;
    await fetch(`${getApiBase()}/streams/${cameraId}/hls/release?${authParam}`);
  } catch {
    // Best-effort release — don't throw if the backend is unreachable
  }
}

/**
 * Temporary function to wipe all alerts and detections from the database.
 */
export async function deleteAllLogs() {
  const res = await authFetch(`${getApiBase()}/detections?confirm=DELETE_ALL_LOGS`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete logs');
  return res.json();
}

/**
 * Check if the backend pipeline workers are actively running.
 */
export async function fetchSystemStatus() {
  const res = await authFetch(`${getApiBase()}/system/status`);
  if (!res.ok) throw new Error(`GET /system/status failed: ${res.status}`);
  return res.json();
}

/**
 * Start or stop backend scanning workers.
 */
export async function toggleScan(scanning) {
  const res = await authFetch(`${getApiBase()}/system/scan`, {
    method: 'POST',
    body: JSON.stringify({ scanning }),
  });
  if (!res.ok) throw new Error(`POST /system/scan failed: ${res.status}`);
  return res.json();
}

/**
 * Start or stop the backend scanning worker for a specific camera.
 */
export async function toggleCameraScan(cameraId, scanning) {
  const res = await authFetch(`${getApiBase()}/system/scan/${cameraId}`, {
    method: 'POST',
    body: JSON.stringify({ scanning }),
  });
  if (!res.ok) throw new Error(`POST /system/scan/${cameraId} failed: ${res.status}`);
  return res.json();
}

// ── Videos (Offline) ─────────────────────────────────────
export async function uploadVideo(file) {
  const formData = new FormData();
  formData.append('file', file);
  
  const uploadHeaders = { ...getHeaders() };
  delete uploadHeaders['Content-Type'];

  const res = await authFetch(`${getApiBase()}/videos/upload`, {
    method: 'POST',
    headers: uploadHeaders,
    body: formData,
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    let errMsg = `POST /videos/upload failed: ${res.status}`;
    if (errorData.detail) {
      errMsg = Array.isArray(errorData.detail) 
        ? errorData.detail.map(d => d.msg).join(', ') 
        : errorData.detail;
    }
    throw new Error(errMsg);
  }
  return res.json();
}
export async function fetchVideos() {
  const res = await authFetch(`${getApiBase()}/videos/list`);
  if (!res.ok) throw new Error(`GET /videos/list failed: ${res.status}`);
  return res.json();
}

export async function deleteVideo(videoId) {
  const res = await authFetch(`${getApiBase()}/videos/delete/${videoId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`DELETE /videos/delete/${videoId} failed: ${res.status}`);
  return res.json();
}

export function getVideoPlayUrl(videoId) {
  const accessToken = getAccessToken();
  const authParam = accessToken
    ? `token=${encodeURIComponent(accessToken)}`
    : `api_key=${encodeURIComponent(getApiKey() || "")}`;
  return `${getApiBase()}/videos/play/${videoId}?${authParam}`;
}
// ── Users Management ───────────────────────────────────────
export async function fetchUsers() {
  const res = await authFetch(`${getApiBase()}/auth/users`);
  if (!res.ok) throw new Error(`GET /auth/users failed: ${res.status}`);
  return res.json();
}

export async function registerUser(username, password, role) {
  const res = await fetch(`${getApiBase()}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, role }),
  });
  if (!res.ok) {
    const errorData = await res.json();
    throw new Error(errorData.detail || 'Failed to register user');
  }
  return res.json();
}
/**
 * Start or stop the backend scanning worker for a specific offline video file.
 */
export async function toggleVideoScan(videoId, scanning) {
  const res = await authFetch(`${getApiBase()}/system/scan/video/${videoId}`, {
    method: 'POST',
    body: JSON.stringify({ scanning }),
  });
  if (!res.ok) throw new Error(`POST /system/scan/video/${videoId} failed: ${res.status}`);
  return res.json();
}





