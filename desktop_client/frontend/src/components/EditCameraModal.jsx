import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X, Save, Loader2, Camera as CameraIcon, MapPin } from 'lucide-react';
import { MapContainer, TileLayer, useMapEvents, Marker } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Fix default marker icon issue in leaflet
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

function MapClickHandler({ onLocationSelect }) {
  useMapEvents({
    click(e) {
      onLocationSelect(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

export default function EditCameraModal({ isOpen, onClose, onSave, camera, isLoading }) {
  const [editData, setEditData] = useState({});
  const [isMapOpen, setIsMapOpen] = useState(false);

  useEffect(() => {
    if (camera) {
      setEditData(camera);
    }
  }, [camera]);

  if (!isOpen || !camera) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!editData.name || !editData.stream_url || !editData.city || !editData.district || !editData.location || !editData.department || !editData.department_id || editData.latitude == null || editData.longitude == null) {
      alert("Name, Stream URL, City, District, Location, Department Name, Department ID, Latitude, and Longitude are required.");
      return;
    }
    const ALLOWED_PROTOCOLS = ['rtsp://', 'rtsps://', 'http://', 'https://'];
    const streamUrl = (editData.stream_url || '').trim();
    if (!ALLOWED_PROTOCOLS.some(proto => streamUrl.startsWith(proto))) {
      alert("Stream URL must start with rtsp://, rtsps://, http://, or https://");
      return;
    }
    onSave(camera.camera_id, editData);
  };

  return createPortal(
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      
      {/* Map Picker Modal */}
      {isMapOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50" onClick={() => setIsMapOpen(false)}>
          <div className="bg-bg-secondary w-full max-w-2xl rounded-xl shadow-2xl flex flex-col h-[70vh] border border-border-secondary overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="p-4 border-b border-border-secondary flex justify-between items-center bg-bg-elevated">
              <h3 className="font-semibold text-text-bright flex items-center gap-2"><MapPin className="w-4 h-4 text-accent" /> Pick Location</h3>
              <button onClick={() => setIsMapOpen(false)} className="text-text-muted hover:text-danger"><X className="w-5 h-5" /></button>
            </div>
            <div className="flex-1 relative">
              <MapContainer center={[23.2156, 72.6369]} zoom={7} style={{ height: '100%', width: '100%' }}>
                <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; OpenStreetMap contributors' />
                <MapClickHandler onLocationSelect={(lat, lng) => {
                  setEditData({...editData, latitude: parseFloat(lat.toFixed(6)), longitude: parseFloat(lng.toFixed(6))});
                  setIsMapOpen(false);
                }} />
                {editData.latitude && editData.longitude && (
                  <Marker position={[editData.latitude, editData.longitude]} />
                )}
              </MapContainer>
            </div>
            <div className="p-3 bg-bg-primary text-xs text-text-secondary text-center border-t border-border-secondary">
              Click anywhere on the map to select coordinates
            </div>
          </div>
        </div>
      )}

      <div className="bg-bg-secondary w-full max-w-lg rounded-xl shadow-2xl flex flex-col max-h-[90vh] border border-border-secondary overflow-hidden" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-primary bg-bg-secondary shrink-0">
          <div className="flex items-center gap-2 text-text-bright">
            <CameraIcon className="w-5 h-5" />
            <h2 className="text-sm font-semibold uppercase tracking-wide">Edit Camera #{camera.camera_id}</h2>
          </div>
          <button 
            onClick={onClose}
            className="p-1 text-text-secondary hover:text-text-bright hover:bg-bg-hover rounded-md transition-colors"
            disabled={isLoading}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <div className="p-5 overflow-y-auto scrollbar-thin">
          <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="block text-xs font-medium text-text-secondary mb-1">Camera Name *</label>
              <input type="text" value={editData.name || ''} onChange={e => setEditData({...editData, name: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" required />
            </div>

            <div className="col-span-2">
              <label className="block text-xs font-medium text-text-secondary mb-1">Stream URL *</label>
              <input type="text" value={editData.stream_url || ''} onChange={e => setEditData({...editData, stream_url: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" required />
            </div>

            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1">Department ID *</label>
              <input type="number" value={editData.department_id || ''} onChange={e => setEditData({...editData, department_id: e.target.value ? parseInt(e.target.value) : null})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" required />
            </div>
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1">Department Name *</label>
              <input type="text" value={editData.department || ''} onChange={e => setEditData({...editData, department: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" required />
            </div>

            <div className="col-span-2">
              <label className="block text-xs font-medium text-text-secondary mb-1">Location *</label>
              <input type="text" value={editData.location || ''} onChange={e => setEditData({...editData, location: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" required />
            </div>

            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1">City *</label>
              <input type="text" value={editData.city || ''} onChange={e => setEditData({...editData, city: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" required />
            </div>
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1">District *</label>
              <select value={editData.district || ''} onChange={e => setEditData({...editData, district: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" required>
                <option value="">Select District</option>
                {['Ahmedabad', 'Amreli', 'Anand', 'Aravalli', 'Banaskantha', 'Bharuch', 'Bhavnagar', 'Botad', 'Chhota Udaipur', 'Dahod', 'Dang', 'Devbhoomi Dwarka', 'Gandhinagar', 'Gir Somnath', 'Jamnagar', 'Junagadh', 'Kheda', 'Kutch', 'Mahisagar', 'Mehsana', 'Morbi', 'Narmada', 'Navsari', 'Panchmahal', 'Patan', 'Porbandar', 'Rajkot', 'Sabarkantha', 'Surat', 'Surendranagar', 'Tapi', 'Vadodara', 'Valsad'].map(d => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
            </div>

            <div className="col-span-2 flex justify-between items-end mt-2">
              <label className="block text-xs font-medium text-text-secondary">Coordinates *</label>
              <button type="button" onClick={() => setIsMapOpen(true)} className="text-xs flex items-center gap-1 text-accent hover:text-accent-hover font-medium">
                <MapPin className="w-3 h-3" /> Pick on Map
              </button>
            </div>
            <div>
              <input type="number" step="0.000001" placeholder="Latitude" value={editData.latitude || ''} onChange={e => setEditData({...editData, latitude: e.target.value ? parseFloat(e.target.value) : null})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" required />
            </div>
            <div>
              <input type="number" step="0.000001" placeholder="Longitude" value={editData.longitude || ''} onChange={e => setEditData({...editData, longitude: e.target.value ? parseFloat(e.target.value) : null})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" required />
            </div>

            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1">Connectivity</label>
              <input type="text" value={editData.connectivity || ''} onChange={e => setEditData({...editData, connectivity: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" placeholder="e.g. 5G, Fiber" />
            </div>
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1">Local Storage</label>
              <input type="text" value={editData.storage_details || ''} onChange={e => setEditData({...editData, storage_details: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" placeholder="e.g. 1TB NVR" />
            </div>

            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1">Camera Type</label>
              <input type="text" value={editData.camera_type || ''} onChange={e => setEditData({...editData, camera_type: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" placeholder="e.g. PTZ, Dome" />
            </div>
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1">Status</label>
              <select value={editData.status || 'active'} onChange={e => setEditData({...editData, status: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent">
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
                <option value="error">Error</option>
              </select>
            </div>
          </div>
          <button 
            type="submit"
            disabled={isLoading}
            className="w-full mt-2 py-2 px-4 rounded-md bg-accent text-white hover:bg-accent-hover transition-all font-medium text-sm flex items-center justify-center gap-2"
          >
            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save Changes
          </button>
        </form>
        </div>
      </div>
    </div>,
    document.body
  );
}
