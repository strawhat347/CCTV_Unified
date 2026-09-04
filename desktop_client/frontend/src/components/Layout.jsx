import { useState, useCallback, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Navbar from './Navbar';
import AlertPanel from './AlertPanel';
import AIPanel from './AIPanel';
import CameraManagementModal from './CameraManagementModal';
import { addCamera, importCamerasCsv, deleteAllCameras } from '../services/api';
import { toast } from './Toast';
import { confirmModal } from './ConfirmModal';

export default function Layout() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [rightPanel, setRightPanel] = useState(null);
  const [alertCount, setAlertCount] = useState(0);
  const [manageModalOpen, setManageModalOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const toggleSidebar = () => setIsSidebarOpen(!isSidebarOpen);
  const toggleAlertPanel = () => setRightPanel((prev) => (prev === 'alerts' ? null : 'alerts'));
  const toggleAIPanel = () => setRightPanel((prev) => (prev === 'ai' ? null : 'ai'));

  const handleAlertCountChange = useCallback((count) => {
    setAlertCount(count);
  }, []);

  useEffect(() => {
    const handleOpenManage = () => setManageModalOpen(true);
    window.addEventListener('openManageCameras', handleOpenManage);
    return () => window.removeEventListener('openManageCameras', handleOpenManage);
  }, []);

  const handleAddCamera = async (cameraData) => {
    try {
      setLoading(true);
      await addCamera(cameraData);
      window.dispatchEvent(new CustomEvent('camerasChanged'));
      setManageModalOpen(false);
      toast.success('Camera added successfully!');
    } catch (err) {
      toast.error(`Failed to add camera: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleCsvImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      setLoading(true);
      await importCamerasCsv(file);
      window.dispatchEvent(new CustomEvent('camerasChanged'));
      setManageModalOpen(false);
      toast.success('Cameras imported successfully!');
    } catch (err) {
      toast.error(`Import failed: ${err.message}`);
    } finally {
      setLoading(false);
      e.target.value = null;
    }
  };

  const handleClearAll = async () => {
    const ok = await confirmModal({
      title: 'Delete All Cameras',
      message: 'Are you sure you want to delete all cameras? This will also delete detections and alerts.',
      confirmText: 'Delete All',
      isDanger: true,
    });
    if (!ok) return;

    try {
      setLoading(true);
      await deleteAllCameras();
      window.dispatchEvent(new CustomEvent('camerasChanged'));
      setManageModalOpen(false);
      toast.success('All cameras deleted!');
    } catch (err) {
      toast.error(`Clear failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-bg-primary text-text-primary h-screen w-screen overflow-hidden flex flex-col font-sans">
      <Navbar 
        alertCount={alertCount} 
        onToggleAlertPanel={toggleAlertPanel} 
        onToggleAIPanel={toggleAIPanel} 
        rightPanel={rightPanel}
        onOpenAddCamera={() => setManageModalOpen(true)}
      />
      <div className="flex-1 flex min-h-0 overflow-hidden relative">
        {/* Invisible backdrop to capture clicks outside the sidebar */}
        {isSidebarOpen && (
          <div 
            className="fixed inset-0 z-[90]" 
            onClick={() => setIsSidebarOpen(false)}
          ></div>
        )}
        <Sidebar isOpen={isSidebarOpen} toggleSidebar={toggleSidebar} />
        <div className="flex-1 min-w-0 overflow-hidden pl-12">
          <Outlet />
        </div>
        {rightPanel === 'alerts' && <AlertPanel onClose={() => setRightPanel(null)} onAlertCountChange={handleAlertCountChange} />}
        {rightPanel === 'ai' && <AIPanel onClose={() => setRightPanel(null)} />}
      </div>

      <CameraManagementModal
        isOpen={manageModalOpen}
        onClose={() => setManageModalOpen(false)}
        onImport={handleCsvImport}
        onClearAll={handleClearAll}
        onAddCamera={handleAddCamera}
        isLoading={loading}
      />
    </div>
  );
}
