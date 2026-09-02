import React, { useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X, Upload, Loader2 } from 'lucide-react';
import { getApiBase, getApiKey } from '../services/api';

export default function VideoManagementModal({ isOpen, onClose, onUploaded }) {
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef(null);

  if (!isOpen) return null;

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const res = await fetch(`${getApiBase()}/videos/upload?api_key=${encodeURIComponent(getApiKey() || "")}`, {
        method: 'POST',
        body: formData
      });
      
      if (!res.ok) throw new Error('Upload failed');
      
      alert('Video uploaded successfully!');
      if (onUploaded) onUploaded();
      onClose();
    } catch (err) {
      alert(`Upload failed: ${err.message}`);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = null;
    }
  };

  return createPortal(
    <div className="fixed inset-0 bg-black/60 z-[200] flex items-center justify-center p-4 backdrop-blur-sm animate-in fade-in duration-200" onClick={onClose}>
      <div className="bg-bg-secondary w-full max-w-md rounded-xl shadow-2xl border border-border-primary overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between p-4 border-b border-border-secondary">
          <h2 className="text-lg font-bold text-text-bright">Video Management</h2>
          <button onClick={onClose} className="p-1 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-hover transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
        
        <div className="p-6 flex flex-col gap-4">
          <div className="flex flex-col items-center justify-center border-2 border-dashed border-border-secondary rounded-xl p-8 bg-bg-primary/50 text-center">
            <Upload className="w-10 h-10 text-text-muted mb-3" />
            <p className="text-sm text-text-secondary mb-4">Select an MP4 or WebM video file to upload for offline viewing.</p>
            
            <input 
              type="file" 
              ref={fileInputRef}
              accept="video/mp4,video/webm"
              onChange={handleUpload}
              className="hidden" 
              id="video-upload"
            />
            <label 
              htmlFor="video-upload"
              className={`px-4 py-2 bg-accent text-white rounded-md text-sm font-medium transition-colors cursor-pointer flex items-center gap-2 ${isUploading ? 'opacity-70 pointer-events-none' : 'hover:bg-accent-hover'}`}
            >
              {isUploading ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Uploading...</>
              ) : (
                'Select Video File'
              )}
            </label>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
