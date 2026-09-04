import { HashRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import VideoWall from './pages/VideoWall';
import VideoFileWall from './pages/VideoFileWall';
import GISRegistry from './pages/GISRegistry';
import LiveLogs from './pages/LiveLogs';
import Login from './pages/Login';

import { useState, useEffect } from 'react';
import { waitForApi, isLoggedIn } from './services/api';
import ToastContainer from './components/Toast';
import ConfirmModalContainer from './components/ConfirmModal';

// Temporary placeholders for incomplete pages
const Playback = () => <div className="p-8 text-text-primary text-xl font-bold">Playback (Coming Soon)</div>;

function App() {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    waitForApi().then(() => {
      setReady(true);
      setAuthenticated(isLoggedIn());
    });
  }, []);

  if (!ready) {
    return <div className="h-screen w-screen bg-bg-primary flex items-center justify-center text-text-muted">Loading Desktop Environment...</div>;
  }

  if (!authenticated) {
    return (
      <>
        <ToastContainer />
        <ConfirmModalContainer />
        <Login onLoginSuccess={() => setAuthenticated(true)} />
      </>
    );
  }

  return (
    <>
      <ToastContainer />
      <ConfirmModalContainer />
      <Router>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="live/cameras" element={<VideoWall />} />
            <Route path="live/videos" element={<VideoFileWall />} />
            <Route path="registry" element={<GISRegistry />} />
            <Route path="logs" element={<LiveLogs />} />
            <Route path="playback" element={<Playback />} />
          </Route>
        </Routes>
      </Router>
    </>
  );
}

export default App;


