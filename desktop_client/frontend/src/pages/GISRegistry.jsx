import { useState, useMemo, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { MapContainer, TileLayer, Marker, Popup, Polygon, FeatureGroup, useMapEvents } from 'react-leaflet';
import DrawControl from '../components/DrawControl';

function ClosePopupOnZoom() {
  const map = useMapEvents({
    zoomstart: () => {
      map.closePopup();
    },
  });
  return null;
}
import MarkerClusterGroup from 'react-leaflet-cluster';
import L from 'leaflet';
import { Filter, Flame, Eye, Maximize } from 'lucide-react';
import { fetchCameras, fetchAlerts, getStreamUrl } from '../services/api';
import HeatmapLayer from '../components/HeatmapLayer';

// Leaflet draw styles
import 'leaflet-draw/dist/leaflet.draw.css';

// Fix marker icons for leafet-draw
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

// Helper to create custom HTML markers
const createCustomIcon = (status) => {
  // Using blue dot as requested for individual cameras
  return L.divIcon({
    className: 'custom-leaflet-icon bg-transparent border-0',
    html: `<div class="w-4 h-4 rounded-full border-2 border-white shadow-md bg-accent animate-pulse"></div>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
  });
};

const createCustomClusterIcon = (cluster) => {
  const count = cluster.getChildCount();
  let colorHex = '#f59e0b'; // medium (amber)
  if (count < 10) colorHex = '#2563eb'; // small (blue)
  if (count > 50) colorHex = '#ef4444'; // large (red)
  
  const svgPin = `
    <div class="relative flex justify-center w-10 h-10 group cursor-pointer">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="${colorHex}" class="w-10 h-10 absolute top-0 left-0 drop-shadow-md">
        <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>
      </svg>
      <div class="absolute top-[3px] left-[8px] w-6 h-6 rounded-full bg-white shadow-sm"></div>
      
      <!-- Tooltip rendered below the pin on hover -->
      <div class="absolute top-[42px] px-2.5 py-1 bg-bg-elevated text-text-primary border border-border-secondary shadow-lg rounded-md opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap text-xs font-semibold pointer-events-none z-50">
        ${count} cameras
      </div>
    </div>
  `;
  
  return L.divIcon({
    html: svgPin,
    className: 'custom-leaflet-cluster-icon bg-transparent border-0',
    iconSize: [40, 40],
    iconAnchor: [20, 40],
  });
};

// Helper for FOV Cone
const getFOVCone = (centerLat, centerLng, directionDegrees, fovAngleDegrees, radiusMeters = 150) => {
  const points = [];
  points.push([centerLat, centerLng]);
  
  const startAngle = directionDegrees - fovAngleDegrees / 2;
  const endAngle = directionDegrees + fovAngleDegrees / 2;
  
  const R = 6378137;
  const dLat = radiusMeters / R;
  const dLon = radiusMeters / (R * Math.cos(Math.PI * centerLat / 180));
  
  for (let i = startAngle; i <= endAngle; i += 5) {
    const theta = (i * Math.PI) / 180;
    const lat = centerLat + (dLat * Math.cos(theta)) * (180 / Math.PI);
    const lng = centerLng + (dLon * Math.sin(theta)) * (180 / Math.PI);
    points.push([lat, lng]);
  }
  return points;
};

// Generate mock directions for cameras since DB doesn't have it
const getMockDirection = (cameraId) => {
  // deterministic pseudo-random
  return (cameraId * 73) % 360;
};

// Helper to check if a point is inside a polygon
const isPointInPolygon = (point, vs) => {
  const x = point[1], y = point[0]; // lng, lat
  let inside = false;
  for (let i = 0, j = vs.length - 1; i < vs.length; j = i++) {
    const xi = vs[i].lng, yi = vs[i].lat;
    const xj = vs[j].lng, yj = vs[j].lat;
    const intersect = ((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
};

export default function GISRegistry() {
  const [cameras, setCameras] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterType, setFilterType] = useState('all');
  const [showFilters, setShowFilters] = useState(false);
  const [portalNode, setPortalNode] = useState(null);

  // Layer Toggles
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [showFOV, setShowFOV] = useState(false);
  
  // Geofencing state
  const [selectedCameraIds, setSelectedCameraIds] = useState([]);

  const [searchQuery, setSearchQuery] = useState('');
  
  useEffect(() => {
    setPortalNode(document.getElementById('navbar-actions-portal'));
  }, []);
  
  useEffect(() => {
    fetchCameras(null, searchQuery, 2000, 0)
      .then(data => setCameras(data || []))
      .catch(err => console.error("Failed to load map cameras:", err));
      
    // Fetch active alerts for heatmap
    fetchAlerts(500)
      .then(data => setAlerts(data || []))
      .catch(err => console.error("Failed to load alerts:", err));
  }, [searchQuery]);

  const setSearchQueryRef = useRef();

  useEffect(() => {
    setSearchQueryRef.current = setSearchQuery;
  }, [setSearchQuery]);

  useEffect(() => {
    const handleGlobalSearch = (e) => {
      if (setSearchQueryRef.current) setSearchQueryRef.current(e.detail);
    };
    const handleCamerasChanged = () => {
      fetchCameras(null, '', 2000, 0)
        .then(data => setCameras(data || []))
        .catch(err => console.error("Failed to reload map cameras:", err));
    };

    window.addEventListener('globalSearch', handleGlobalSearch);
    window.addEventListener('camerasChanged', handleCamerasChanged);

    return () => {
      window.removeEventListener('globalSearch', handleGlobalSearch);
      window.removeEventListener('camerasChanged', handleCamerasChanged);
    };
  }, []);

  const filteredCameras = useMemo(() => {
    return cameras.filter((cam) => {
      const matchStatus = filterStatus === 'all' || cam.status === filterStatus;
      const matchType = filterType === 'all' || cam.camera_type === filterType;
      return matchStatus && matchType && cam.latitude != null && cam.longitude != null;
    });
  }, [cameras, filterStatus, filterType]);

  // Generate heatmap points based on active alerts and camera coords
  const heatmapPoints = useMemo(() => {
    if (!showHeatmap) return [];
    return alerts.map(alert => {
      const cam = cameras.find(c => c.camera_id === alert.camera_id);
      if (cam && cam.latitude && cam.longitude) {
        // High severity gets higher intensity
        const intensity = alert.severity === 'high' ? 1.0 : alert.severity === 'medium' ? 0.7 : 0.4;
        return [cam.latitude, cam.longitude, intensity];
      }
      return null;
    }).filter(Boolean);
  }, [alerts, cameras, showHeatmap]);

  const handlePolygonChange = (layer) => {
    if (layer instanceof L.Polygon) {
      const latlngs = layer.getLatLngs()[0];
      // Check which cameras are inside
      const insideIds = filteredCameras.filter(cam => {
        return isPointInPolygon([cam.latitude, cam.longitude], latlngs);
      }).map(c => c.camera_id);
      setSelectedCameraIds(insideIds);
    }
  };

  const launchSelectedInVideoWall = () => {
    if (selectedCameraIds.length === 0) return;
    
    try {
      // Get existing active cameras
      const saved = localStorage.getItem('videowall_activeCameras');
      let activeCameras = saved ? JSON.parse(saved) : [];
      
      // Get the full camera objects for the selected IDs
      const camerasToAdd = filteredCameras.filter(c => selectedCameraIds.includes(c.camera_id));
      
      // Append without duplicates
      const currentIds = new Set(activeCameras.map(c => c.camera_id));
      camerasToAdd.forEach(cam => {
        if (!currentIds.has(cam.camera_id)) {
          activeCameras.push(cam);
        }
      });
      
      localStorage.setItem('videowall_activeCameras', JSON.stringify(activeCameras));
      
      // Navigate to video wall
      window.location.hash = '#/live';
    } catch (e) {
      console.error("Failed to launch in video wall", e);
    }
    
    setSelectedCameraIds([]);
  };

  const navbarActions = portalNode ? createPortal(
    <div className="flex gap-2">
      <button 
        onClick={() => setShowFOV(!showFOV)}
        className={`flex items-center justify-center w-8 h-8 rounded transition-colors ${showFOV ? 'bg-accent text-white' : 'text-text-secondary hover:bg-bg-hover hover:text-text-bright'}`}
        title="Toggle FOV Cones"
      >
        <Eye className="w-4 h-4" />
      </button>
      <button 
        onClick={() => setShowHeatmap(!showHeatmap)}
        className={`flex items-center justify-center w-8 h-8 rounded transition-colors ${showHeatmap ? 'bg-danger text-white' : 'text-text-secondary hover:bg-bg-hover hover:text-text-bright'}`}
        title="Toggle Alert Heatmaps"
      >
        <Flame className="w-4 h-4" />
      </button>
      <button 
        onClick={() => setShowFilters(!showFilters)}
        className={`flex items-center justify-center w-8 h-8 rounded transition-colors ${showFilters ? 'bg-bg-active text-text-bright' : 'text-text-secondary hover:bg-bg-hover hover:text-text-bright'}`}
        title="Map Filters"
      >
        <Filter className="w-4 h-4" />
      </button>
    </div>,
    portalNode
  ) : null;

  return (
    <div className="h-full w-full flex flex-col bg-bg-primary relative">
      {navbarActions}
      
      {/* Main Map Area */}
      <div className="flex-1 relative z-0">
        <MapContainer 
          center={[23.1600, 72.6000]}
          zoom={11} 
          className="h-full w-full z-0"
          zoomControl={false}
        >
          <TileLayer
            attribution='&copy; OpenStreetMap contributors'
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            maxZoom={19}
          />
          
          <ClosePopupOnZoom />

          <DrawControl 
            onChange={handlePolygonChange} 
            clearTrigger={selectedCameraIds.length === 0} 
          />

          {showHeatmap && <HeatmapLayer points={heatmapPoints} />}

          <MarkerClusterGroup
            chunkedLoading
            maxClusterRadius={40}
            disableClusteringAtZoom={15}
            showCoverageOnHover={false}
            iconCreateFunction={createCustomClusterIcon}
          >
            {filteredCameras.map((cam) => (
              <Marker 
                key={cam.camera_id} 
                position={[cam.latitude, cam.longitude]} 
                icon={createCustomIcon(cam.status)}
              >
                <Popup className="rounded-lg shadow-xl border-0 overflow-hidden" minWidth={284}>
                  <div className="p-0 flex flex-col">
                    {/* Live Video Preview instead of just text */}
                    <div className="w-[284px] h-40 bg-black relative">
                      <video 
                        src={getStreamUrl(cam.camera_id)} 
                        className="w-full h-full object-cover"
                        muted 
                        loop
                        controls
                        playsInline
                        onError={(e) => { e.target.poster = '/placeholder.jpg'; }}
                      />
                      <div className="absolute top-2 left-2 px-1.5 py-0.5 bg-black/60 rounded text-xs text-white backdrop-blur">
                        LIVE
                      </div>
                    </div>
                    
                    <div className="p-3 bg-bg-secondary">
                      <h3 className="font-bold text-text-bright text-base mb-1">Camera #{cam.camera_id} {cam.name ? `- ${cam.name}` : ''}</h3>
                      <p className="text-xs text-text-muted mb-2">{cam.location || 'Unknown Location'}</p>
                      
                      <div className="space-y-1.5 text-sm">
                        <div className="flex justify-between">
                          <span className="text-text-secondary">Status:</span>
                          <span className={`font-medium capitalize ${cam.status === 'active' ? 'text-success' : cam.status === 'error' ? 'text-danger' : 'text-warning'}`}>
                            {cam.status}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-text-secondary">Type:</span>
                          <span className="font-medium text-text-primary">{cam.camera_type || 'Unknown'}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-text-secondary">Department:</span>
                          <span className="font-medium text-text-primary">{cam.department || 'Unknown'}</span>
                        </div>
                      </div>

                      <div className="mt-3 pt-3 border-t border-border-secondary">
                        <button 
                          onClick={() => {
                            try {
                              const saved = localStorage.getItem('videowall_activeCameras');
                              let activeCameras = saved ? JSON.parse(saved) : [];
                              if (!activeCameras.find(c => c.camera_id === cam.camera_id)) {
                                activeCameras.push(cam);
                                localStorage.setItem('videowall_activeCameras', JSON.stringify(activeCameras));
                              }
                              window.location.hash = '#/live';
                            } catch (e) {
                              console.error("Failed to launch in video wall", e);
                            }
                          }}
                          className="w-full py-1.5 bg-accent text-white rounded font-medium text-sm hover:bg-accent-hover transition-colors"
                        >
                          Open in Video Wall
                        </button>
                      </div>
                    </div>
                  </div>
                </Popup>
              </Marker>
            ))}
          </MarkerClusterGroup>

          {/* FOV Cones Layer */}
          {showFOV && filteredCameras.map(cam => (
            <Polygon 
              key={`fov-${cam.camera_id}`}
              positions={getFOVCone(cam.latitude, cam.longitude, getMockDirection(cam.camera_id), 60)} 
              pathOptions={{
                color: '#4f46e5',
                fillColor: '#4f46e5',
                fillOpacity: 0.2,
                weight: 1
              }}
            />
          ))}
        </MapContainer>

        {/* Spatial Selection Overlay */}
        {selectedCameraIds.length > 0 && (
          <div className="absolute bottom-6 left-1/2 -translate-x-1/2 bg-bg-secondary border border-accent rounded-lg shadow-2xl p-4 z-[400] flex items-center gap-4 animate-in slide-in-from-bottom-5">
            <div>
              <h4 className="text-text-bright font-bold">Spatial Selection</h4>
              <p className="text-sm text-text-secondary">{selectedCameraIds.length} camera(s) selected in geofence.</p>
            </div>
            <div className="flex gap-2">
              <button 
                onClick={() => setSelectedCameraIds([])}
                className="px-4 py-2 bg-bg-elevated text-text-primary rounded font-medium text-sm hover:bg-bg-hover transition-colors"
              >
                Clear
              </button>
              <button 
                onClick={launchSelectedInVideoWall}
                className="flex items-center gap-2 px-4 py-2 bg-accent text-white rounded font-medium text-sm hover:bg-accent-hover transition-colors"
              >
                <Maximize className="w-4 h-4" />
                Launch Wall
              </button>
            </div>
          </div>
        )}

        {/* Floating Filter Panel */}
        {showFilters && (
          <div className="absolute top-4 right-4 bg-bg-secondary border border-border-primary rounded-lg shadow-lg p-4 w-64 z-[400]">
            <div className="flex items-center gap-2 mb-4 pb-2 border-b border-border-secondary">
              <Filter className="w-4 h-4 text-text-secondary" />
              <h3 className="font-semibold text-text-bright text-sm">Map Filters</h3>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-text-secondary mb-1.5 uppercase tracking-wider">Status</label>
                <select 
                  value={filterStatus} 
                  onChange={(e) => setFilterStatus(e.target.value)}
                  className="w-full bg-bg-primary border border-border-secondary rounded px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent"
                >
                  <option value="all">All Statuses</option>
                  <option value="active">Active Only</option>
                  <option value="inactive">Inactive Only</option>
                  <option value="error">Error</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-text-secondary mb-1.5 uppercase tracking-wider">Camera Type</label>
                <select 
                  value={filterType} 
                  onChange={(e) => setFilterType(e.target.value)}
                  className="w-full bg-bg-primary border border-border-secondary rounded px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent"
                >
                  <option value="all">All Types</option>
                  <option value="PTZ">PTZ</option>
                  <option value="ANPR">ANPR</option>
                  <option value="Dome">Dome</option>
                  <option value="Bullet">Bullet</option>
                </select>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
