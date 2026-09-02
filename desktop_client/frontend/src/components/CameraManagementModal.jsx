import { useState } from 'react';
import { createPortal } from 'react-dom';
import { X, UploadCloud, Trash2, AlertTriangle, Loader2, Plus, Camera as CameraIcon, MapPin } from 'lucide-react';
import { MapContainer, TileLayer, useMapEvents, Marker } from 'react-leaflet';
import L from 'leaflet';

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

export default function CameraManagementModal({ isOpen, onClose, onImport, onClearAll, onAddCamera, isLoading }) {
  const [activeTab, setActiveTab] = useState('add'); // 'add', 'import', 'delete'
  const [selectedFile, setSelectedFile] = useState(null);
  const [isMapOpen, setIsMapOpen] = useState(false);
  const [newCamera, setNewCamera] = useState({
    name: '',
    stream_url: '',
    location: '',
    department: '',
    camera_type: 'Dome',
    status: 'active'
  });

  if (!isOpen) return null;

  const handleAddSubmit = (e) => {
    e.preventDefault();
    if (!newCamera.name || !newCamera.stream_url || !newCamera.city || !newCamera.district || !newCamera.location || !newCamera.department || !newCamera.department_id || newCamera.latitude == null || newCamera.longitude == null) {
      alert("Name, Stream URL, City, District, Location, Department Name, Department ID, Latitude, and Longitude are required.");
      return;
    }
    if (!newCamera.stream_url.startsWith('https://') && !newCamera.stream_url.startsWith('rtsps://')) {
      alert("Stream URL must be a secure remote URL (https:// or rtsps://). Local files, unencrypted connections, or mock protocols are no longer allowed.");
      return;
    }
    onAddCamera(newCamera);
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
                  setNewCamera({...newCamera, latitude: parseFloat(lat.toFixed(6)), longitude: parseFloat(lng.toFixed(6))});
                  setIsMapOpen(false);
                }} />
                {newCamera.latitude && newCamera.longitude && (
                  <Marker position={[newCamera.latitude, newCamera.longitude]} />
                )}
              </MapContainer>
            </div>
            <div className="p-3 bg-bg-primary text-xs text-text-secondary text-center border-t border-border-secondary">
              Click anywhere on the map to select coordinates
            </div>
          </div>
        </div>
      )}

      <div className="bg-bg-elevated border border-border-secondary rounded-xl shadow-2xl w-full max-w-md max-h-[90vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-primary bg-bg-secondary shrink-0">
          <div className="flex items-center gap-2 text-text-bright">
            <CameraIcon className="w-5 h-5" />
            <h2 className="text-sm font-semibold uppercase tracking-wide">Manage Cameras</h2>
          </div>
          <button 
            onClick={onClose}
            className="p-1 text-text-secondary hover:text-text-bright hover:bg-bg-hover rounded-md transition-colors"
            disabled={isLoading}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border-secondary shrink-0">
          <button 
            onClick={() => setActiveTab('add')}
            className={`flex-1 py-2.5 text-xs font-semibold uppercase tracking-wider transition-colors ${
              activeTab === 'add' ? 'text-accent border-b-2 border-accent bg-accent/5' : 'text-text-secondary hover:text-text-primary hover:bg-bg-hover'
            }`}
          >
            Add Camera
          </button>
          <button 
            onClick={() => setActiveTab('import')}
            className={`flex-1 py-2.5 text-xs font-semibold uppercase tracking-wider transition-colors ${
              activeTab === 'import' ? 'text-accent border-b-2 border-accent bg-accent/5' : 'text-text-secondary hover:text-text-primary hover:bg-bg-hover'
            }`}
          >
            Import CSV
          </button>
          <button 
            onClick={() => setActiveTab('delete')}
            className={`flex-1 py-2.5 text-xs font-semibold uppercase tracking-wider transition-colors ${
              activeTab === 'delete' ? 'text-danger border-b-2 border-danger bg-danger/5' : 'text-text-secondary hover:text-danger hover:bg-bg-hover'
            }`}
          >
            Delete
          </button>
        </div>

        {/* Content Area */}
        <div className="p-5 overflow-y-auto scrollbar-thin">
          {activeTab === 'add' && (
            <form onSubmit={handleAddSubmit} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <label className="block text-xs font-medium text-text-secondary mb-1">Camera Name *</label>
                  <input type="text" value={newCamera.name} onChange={e => setNewCamera({...newCamera, name: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" required />
                </div>

                <div className="col-span-2">
                  <label className="block text-xs font-medium text-text-secondary mb-1">Stream URL *</label>
                  <input type="text" value={newCamera.stream_url} onChange={e => setNewCamera({...newCamera, stream_url: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" required />
                </div>

                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1">Department ID *</label>
                  <input type="number" value={newCamera.department_id || ''} onChange={e => setNewCamera({...newCamera, department_id: e.target.value ? parseInt(e.target.value) : null})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" required />
                </div>
                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1">Department Name *</label>
                  <input type="text" value={newCamera.department || ''} onChange={e => setNewCamera({...newCamera, department: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" required />
                </div>

                <div className="col-span-2">
                  <label className="block text-xs font-medium text-text-secondary mb-1">Location *</label>
                  <input type="text" value={newCamera.location || ''} onChange={e => setNewCamera({...newCamera, location: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" required />
                </div>

                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1">City *</label>
                  <input type="text" value={newCamera.city || ''} onChange={e => setNewCamera({...newCamera, city: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" required />
                </div>
                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1">District *</label>
                  <select value={newCamera.district || ''} onChange={e => setNewCamera({...newCamera, district: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" required>
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
                    <input type="number" step="0.000001" placeholder="Latitude" value={newCamera.latitude || ''} onChange={e => setNewCamera({...newCamera, latitude: e.target.value ? parseFloat(e.target.value) : null})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" required />
                  </div>
                  <div>
                    <input type="number" step="0.000001" placeholder="Longitude" value={newCamera.longitude || ''} onChange={e => setNewCamera({...newCamera, longitude: e.target.value ? parseFloat(e.target.value) : null})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" required />
                  </div>

                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1">Connectivity</label>
                  <input type="text" value={newCamera.connectivity || ''} onChange={e => setNewCamera({...newCamera, connectivity: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" placeholder="e.g. 5G, Fiber" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1">Local Storage</label>
                  <input type="text" value={newCamera.storage_details || ''} onChange={e => setNewCamera({...newCamera, storage_details: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" placeholder="e.g. 1TB NVR" />
                </div>

                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1">Camera Type</label>
                  <input type="text" value={newCamera.camera_type || ''} onChange={e => setNewCamera({...newCamera, camera_type: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent" placeholder="e.g. PTZ, Dome" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1">Status</label>
                  <select value={newCamera.status} onChange={e => setNewCamera({...newCamera, status: e.target.value})} className="w-full bg-bg-primary border border-border-secondary rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent">
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
                {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                Add Camera
              </button>
            </form>
          )}

          {activeTab === 'import' && (
            <div className="space-y-4">
              <p className="text-sm text-text-secondary">Upload a CSV file to add cameras in bulk. Supported headers: name, stream_url, location, department, camera_type, etc.</p>
              
              {!selectedFile ? (
                <label className={`
                  border-2 border-dashed border-border-secondary rounded-lg p-8 
                  flex flex-col items-center justify-center gap-3 cursor-pointer
                  transition-colors group mt-2
                  ${isLoading ? 'opacity-50 cursor-not-allowed' : 'hover:border-accent hover:bg-accent/5'}
                `}>
                  <UploadCloud className="w-10 h-10 text-text-muted group-hover:text-accent transition-colors" />
                  <span className="text-sm font-medium text-text-secondary group-hover:text-accent transition-colors">
                    Click to select CSV file
                  </span>
                  <input 
                    type="file" 
                    accept=".csv" 
                    className="hidden" 
                    onChange={e => {
                      if (e.target.files?.[0]) setSelectedFile(e.target.files[0]);
                    }} 
                    disabled={isLoading} 
                  />
                </label>
              ) : (
                <div className="p-4 border rounded-lg border-border-secondary bg-bg-secondary/50 mt-2">
                  <div className="flex justify-between items-center mb-4">
                    <div>
                      <span className="block font-medium text-sm text-text-primary truncate pr-4">{selectedFile.name}</span>
                      <span className="block text-xs text-text-muted mt-0.5">{(selectedFile.size / 1024).toFixed(1)} KB</span>
                    </div>
                    <button onClick={() => setSelectedFile(null)} className="text-text-muted hover:text-danger p-1 rounded-md hover:bg-danger/10 transition-colors">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <button 
                    onClick={() => {
                      const pseudoEvent = { target: { files: [selectedFile], value: null } };
                      onImport(pseudoEvent).then(() => setSelectedFile(null));
                    }}
                    disabled={isLoading}
                    className="w-full py-2 bg-accent text-white rounded-md text-sm font-medium hover:bg-accent-hover transition-colors flex items-center justify-center gap-2"
                  >
                    {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <UploadCloud className="w-4 h-4" />}
                    Confirm Import
                  </button>
                </div>
              )}
            </div>
          )}

          {activeTab === 'delete' && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-danger p-3 bg-danger/10 rounded-md border border-danger/20">
                <AlertTriangle className="w-5 h-5 shrink-0" />
                <p className="text-sm font-medium">Permanently delete all cameras from the database. This action will also cascade and delete all associated detections and alerts.</p>
              </div>
              
              <button 
                onClick={onClearAll}
                disabled={isLoading}
                className="w-full mt-4 py-2 px-4 rounded-md bg-danger text-white hover:bg-red-600 transition-all font-medium text-sm flex items-center justify-center gap-2"
              >
                {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                Delete All Cameras
              </button>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
