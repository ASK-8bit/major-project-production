import React, { useState, useEffect } from 'react';
import { authAPI } from './services/api';
import Auth from './components/Auth';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import RepoUpload from './components/RepoUpload';
import { X, Database, GitBranch } from 'lucide-react';

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  
  // Navigation contexts
  const [activeRepoId, setActiveRepoId] = useState(null);
  const [activeChatId, setActiveChatId] = useState(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  // Modals state
  const [showUploadModal, setShowUploadModal] = useState(false);

  // Verify auth on mount
  useEffect(() => {
    const checkAuth = async () => {
      const token = localStorage.getItem('access_token');
      if (!token) {
        setLoading(false);
        return;
      }
      try {
        const data = await authAPI.me();
        setUser(data);
      } catch (err) {
        console.error('Session verification failed:', err);
        // Clear tokens
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
      } finally {
        setLoading(false);
      }
    };

    checkAuth();
  }, []);

  // Listen to background auth failures (e.g. refresh token expired)
  useEffect(() => {
    const handleAuthFailure = () => {
      setUser(null);
      setActiveRepoId(null);
      setActiveChatId(null);
    };

    window.addEventListener('auth-failed', handleAuthFailure);
    return () => window.removeEventListener('auth-failed', handleAuthFailure);
  }, []);

  const handleLogout = async () => {
    if (window.confirm('Are you sure you want to log out?')) {
      try {
        await authAPI.logout();
      } catch (err) {
        console.error('Logout error:', err);
      } finally {
        setUser(null);
        setActiveRepoId(null);
        setActiveChatId(null);
      }
    }
  };

  const handleAuthSuccess = (userData) => {
    setUser(userData);
  };

  const handleUploadSuccess = (sessionId) => {
    setShowUploadModal(false);
    setRefreshTrigger(prev => prev + 1);
    
    if (sessionId) {
      // Just activate the repo — the user will create a session from the sidebar or ChatArea
      setActiveChatId(null);
      setActiveRepoId(sessionId);
    }
  };

  if (loading) {
    return (
      <div 
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          width: '100vw',
          height: '100vh',
          backgroundColor: 'var(--bg-primary)',
          color: 'var(--text-secondary)'
        }}
      >
        <span className="spinner" style={{ width: '28px', height: '28px', borderWidth: '3px', marginBottom: '16px' }} />
        <span style={{ fontSize: '14px', fontWeight: 500 }}>Verifying Session...</span>
      </div>
    );
  }

  // Not logged in -> Show login/register screen
  if (!user) {
    return <Auth onAuthSuccess={handleAuthSuccess} />;
  }

  return (
    <div className="app-layout">
      {/* Sidebar Component */}
      <Sidebar 
        user={user}
        activeRepoId={activeRepoId}
        setActiveRepoId={setActiveRepoId}
        activeChatId={activeChatId}
        setActiveChatId={setActiveChatId}
        onLogout={handleLogout}
        onUploadClick={() => setShowUploadModal(true)}
        refreshTrigger={refreshTrigger}
        setRefreshTrigger={setRefreshTrigger}
      />

      {/* Main Workspace Area */}
      <div className="main-workspace">
        {/* Workspace Header */}
        <div className="workspace-header">
          <div className="active-repo-indicator">
            <GitBranch size={16} style={{ color: activeRepoId ? 'var(--accent-green)' : 'var(--text-muted)' }} />
            {activeRepoId ? (
              <span>Code Index Mode</span>
            ) : (
              <span>No codebase active</span>
            )}
          </div>
          {/* Theme Switcher and controls are embedded inside sidebar, or we could add more header links here */}
        </div>

        {/* Chat Area Component */}
        <ChatArea 
          user={user}
          activeRepoId={activeRepoId}
          activeChatId={activeChatId}
          setActiveChatId={setActiveChatId}
          onOpenUploadModal={() => setShowUploadModal(true)}
          refreshTrigger={refreshTrigger}
          setRefreshTrigger={setRefreshTrigger}
        />
      </div>

      {/* Repo Upload Modal Overlay */}
      {showUploadModal && (
        <div className="modal-overlay" onClick={() => setShowUploadModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Database size={18} style={{ color: 'var(--accent-green)' }} />
                <span>Index a New Repository</span>
              </div>
              <button 
                className="icon-btn" 
                title="Close"
                onClick={() => setShowUploadModal(false)}
              >
                <X size={18} />
              </button>
            </div>
            <div className="modal-body">
              <RepoUpload onUploadSuccess={handleUploadSuccess} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
