import React, { useEffect, useState, useCallback } from 'react';
import { uploadAPI, chatAPI } from '../services/api';
import { 
  GitBranch, Plus, MessageSquare, Trash2, LogOut, Sun, Moon, Database, ChevronDown, ChevronRight, Loader2
} from 'lucide-react';

const Sidebar = ({ 
  user,
  activeRepoId, 
  setActiveRepoId, 
  activeChatId, 
  setActiveChatId, 
  onLogout,
  onUploadClick,
  refreshTrigger,
  setRefreshTrigger
}) => {
  const [repos, setRepos] = useState([]);
  const [chatsByRepo, setChatsByRepo] = useState({});
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [creatingChat, setCreatingChat] = useState(false);

  // Fetch repositories
  const fetchRepos = useCallback(async () => {
    try {
      const data = await uploadAPI.listSessions();
      setRepos(data.sessions || []);
    } catch (err) {
      console.error('Failed to load repositories:', err);
    }
  }, []);

  // Fetch chats for a repository (no auto-select side effect)
  const fetchChats = useCallback(async (repoId) => {
    try {
      const data = await chatAPI.listChats(repoId);
      const chatsList = data.chats || [];
      setChatsByRepo(prev => ({
        ...prev,
        [repoId]: chatsList
      }));
      return chatsList;
    } catch (err) {
      console.error(`Failed to load chats for repo ${repoId}:`, err);
      return [];
    }
  }, []);

  // Re-fetch repos on mount and when refresh is triggered
  useEffect(() => {
    fetchRepos();
  }, [refreshTrigger, fetchRepos]);

  // Fetch chats when the active repo changes (but do NOT auto-select/create chat here)
  useEffect(() => {
    if (activeRepoId) {
      fetchChats(activeRepoId);
    }
  }, [activeRepoId, fetchChats]);

  // Also re-fetch chats for active repo on refreshTrigger (e.g. after new chat created)
  useEffect(() => {
    if (activeRepoId && refreshTrigger > 0) {
      fetchChats(activeRepoId);
    }
  }, [refreshTrigger, activeRepoId, fetchChats]);

  // Handle repository selection/toggle
  const handleRepoClick = (repo) => {
    if (repo.status !== 'ready') {
      alert(`Repository indexing is in progress (status: ${repo.status}). Please wait for it to complete before starting a session.`);
      return;
    }
    
    const repoId = repo.session_id;
    if (activeRepoId === repoId) {
      // Already active — just toggle collapse (don't re-create chats)
      return;
    }
    
    // Switch to a new repo
    setActiveChatId(null);
    setActiveRepoId(repoId);
  };

  // Handle creating new chat thread
  const handleNewChat = async (repoId, e) => {
    if (e) e.stopPropagation();
    if (creatingChat) return;
    setCreatingChat(true);
    try {
      const newChatRes = await chatAPI.newChat(repoId);
      // Refresh chats for this repo
      const updatedChats = await fetchChats(repoId);
      setActiveChatId(newChatRes.chat_id);
      // Make sure this repo is active
      if (activeRepoId !== repoId) {
        setActiveRepoId(repoId);
      }
    } catch (err) {
      console.error('Failed to create new chat:', err);
      alert(err.response?.data?.detail || 'Failed to create new chat session.');
    } finally {
      setCreatingChat(false);
    }
  };

  // Handle delete repo session
  const handleDeleteRepo = async (repoId, repoName, e) => {
    e.stopPropagation();
    if (window.confirm(`Are you sure you want to remove the index and chats for "${repoName}"?`)) {
      try {
        await uploadAPI.deleteSession(repoId);
        if (activeRepoId === repoId) {
          setActiveRepoId(null);
          setActiveChatId(null);
        }
        setChatsByRepo(prev => {
          const updated = { ...prev };
          delete updated[repoId];
          return updated;
        });
        setRefreshTrigger(prev => prev + 1);
      } catch (err) {
        console.error('Failed to delete session:', err);
        alert('Failed to delete repository index.');
      }
    }
  };

  // Handle delete chat session
  const handleDeleteChat = async (chatId, chatTitle, repoId, e) => {
    e.stopPropagation();
    if (window.confirm(`Are you sure you want to delete the chat session "${chatTitle || 'Untitled Chat'}"?`)) {
      try {
        await chatAPI.deleteChat(chatId);
        if (activeChatId === chatId) {
          setActiveChatId(null);
        }
        await fetchChats(repoId);
        setRefreshTrigger(prev => prev + 1);
      } catch (err) {
        console.error('Failed to delete chat:', err);
        alert('Failed to delete chat session.');
      }
    }
  };

  // Toggle Dark/Light Mode
  const toggleTheme = (dark) => {
    setIsDarkMode(dark);
    if (dark) {
      document.body.classList.remove('light-mode');
    } else {
      document.body.classList.add('light-mode');
    }
  };

  // Extract repo name from github url
  const getRepoDisplayName = (url) => {
    try {
      const parts = url.replace(/\/$/, '').split('/');
      if (parts.length >= 2) {
        return `${parts[parts.length - 2]}/${parts[parts.length - 1]}`;
      }
      return url;
    } catch (e) {
      return url;
    }
  };

  return (
    <div className="sidebar">
      {/* Sidebar Header */}
      <div className="sidebar-header">
        <div className="brand-section">
          <div className="brand-title">
            <span>{`{ }`}</span> CodeRAG
          </div>
        </div>
        <button className="new-chat-btn" onClick={onUploadClick}>
          <Plus size={16} />
          <span>Upload New Repo</span>
        </button>
      </div>

      {/* Sidebar Scroll Area */}
      <div className="sidebar-scroll">
        <div>
          <div className="section-label">Repositories</div>
          <div className="repo-list">
            {repos.length === 0 ? (
              <div 
                style={{ 
                  padding: '12px 8px', 
                  color: 'var(--text-muted)', 
                  fontSize: '13px', 
                  textAlign: 'center',
                  border: '1px dashed var(--border-color)',
                  borderRadius: '8px'
                }}
              >
                No repositories indexed. Click upload above to add one.
              </div>
            ) : (
              repos.map((repo) => {
                const isActive = activeRepoId === repo.session_id;
                const displayName = getRepoDisplayName(repo.repo_url);
                const repoChats = chatsByRepo[repo.session_id] || [];

                return (
                  <div key={repo.session_id} className={`repo-item-container ${isActive ? 'active' : ''}`}>
                    <div 
                      className="repo-item-header"
                      onClick={() => handleRepoClick(repo)}
                    >
                      <div className="repo-info">
                        {isActive ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                        <GitBranch size={15} style={{ flexShrink: 0, color: isActive ? 'var(--accent-green)' : 'var(--text-muted)' }} />
                        <span className="repo-name" title={repo.repo_url}>{displayName}</span>
                        {repo.status !== 'ready' && (
                          <span style={{ fontSize: '10px', color: 'var(--accent-green)', fontWeight: 600, marginLeft: 'auto', whiteSpace: 'nowrap' }}>
                            indexing...
                          </span>
                        )}
                      </div>
                      
                      <div className="repo-actions">
                        {repo.status === 'ready' && (
                          <button 
                            className="icon-btn" 
                            title="New Chat Session"
                            onClick={(e) => handleNewChat(repo.session_id, e)}
                            disabled={creatingChat}
                          >
                            <Plus size={14} />
                          </button>
                        )}
                        <button 
                          className="icon-btn danger" 
                          title="Delete Repository"
                          onClick={(e) => handleDeleteRepo(repo.session_id, displayName, e)}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>

                    {/* Chats nested under this repo if active */}
                    {isActive && (
                      <div className="repo-chats-container">
                        {/* New Chat trigger within nested repo */}
                        <div 
                          className="chat-item"
                          onClick={(e) => handleNewChat(repo.session_id, e)}
                          style={{ color: 'var(--accent-green)', fontWeight: 500, opacity: creatingChat ? 0.6 : 1 }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            {creatingChat ? <Loader2 size={13} className="spinner" /> : <Plus size={13} />}
                            <span>New Session</span>
                          </div>
                        </div>

                        {repoChats.length === 0 ? (
                          <div style={{ padding: '6px 10px', fontSize: '11px', color: 'var(--text-muted)' }}>
                            No chat sessions yet. Click "New Session" above.
                          </div>
                        ) : (
                          repoChats.map((chat) => (
                            <div 
                              key={chat.chat_id} 
                              className={`chat-item ${activeChatId === chat.chat_id ? 'active' : ''}`}
                              onClick={() => setActiveChatId(chat.chat_id)}
                            >
                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0, flex: 1 }}>
                                <MessageSquare size={13} style={{ flexShrink: 0 }} />
                                <span className="chat-title" title={chat.title || 'Untitled Chat'}>
                                  {chat.title || 'Untitled Chat'}
                                </span>
                              </div>
                              <div className="chat-actions">
                                <button 
                                  className="icon-btn danger" 
                                  title="Delete Chat Session"
                                  onClick={(e) => handleDeleteChat(chat.chat_id, chat.title, repo.session_id, e)}
                                  style={{ padding: '2px' }}
                                >
                                  <Trash2 size={12} />
                                </button>
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* Sidebar Footer */}
      <div className="sidebar-footer">
        {/* Light/Dark Mode Switcher */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '13px' }}>
          <span style={{ color: 'var(--text-secondary)' }}>Appearance</span>
          <div className="theme-mode-toggle">
            <button 
              className={`theme-toggle-btn ${!isDarkMode ? 'active' : ''}`}
              title="Light Mode"
              onClick={() => toggleTheme(false)}
            >
              <Sun size={14} />
            </button>
            <button 
              className={`theme-toggle-btn ${isDarkMode ? 'active' : ''}`}
              title="Dark Mode"
              onClick={() => toggleTheme(true)}
            >
              <Moon size={14} />
            </button>
          </div>
        </div>

        {/* Profile Info */}
        <div className="profile-section">
          <div className="user-details">
            <div className="avatar">
              {(user?.email || 'U').substring(0, 1).toUpperCase()}
            </div>
            <div className="user-email" title={user?.email || ''}>
              {user?.email || 'User'}
            </div>
          </div>
          <button 
            className="icon-btn danger" 
            title="Log Out"
            onClick={onLogout}
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
