import React, { useState, useEffect, useRef, useCallback } from 'react';
import { chatAPI } from '../services/api';
import { 
  Send, Plus, Copy, Check, Code, FileCode,
  HelpCircle, Loader2, MessageSquare, Database
} from 'lucide-react';

const ChatArea = ({ 
  user,
  activeRepoId, 
  activeChatId, 
  setActiveChatId, 
  onOpenUploadModal,
  refreshTrigger,
  setRefreshTrigger
}) => {
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [copiedIndex, setCopiedIndex] = useState(null);
  const [creatingChat, setCreatingChat] = useState(false);
  // Track whether this chat already has a title set (to auto-name only once)
  const titleSetRef = useRef(false);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  // Reset title-set tracker when switching chats
  useEffect(() => {
    titleSetRef.current = false;
  }, [activeChatId]);

  // Load message history when chat changes
  const fetchMessages = useCallback(async () => {
    if (!activeChatId) return;
    try {
      const data = await chatAPI.getMessages(activeChatId);
      const msgs = (data.messages || []).map(msg => {
        if (msg.role === 'assistant') {
          try {
            const parsed = JSON.parse(msg.content);
            if (parsed && typeof parsed === 'object') {
              return {
                ...msg,
                content: parsed.text || msg.content,
                chunks: parsed.chunks || []
              };
            }
          } catch (e) {
            // Content is not JSON, fallback to plain text content
          }
        }
        return msg;
      });
      setMessages(msgs);
      // If the chat already has messages, mark title as already set
      if (msgs.length > 0) {
        titleSetRef.current = true;
      }
    } catch (err) {
      console.error('Failed to fetch messages:', err);
      setMessages([]);
    }
  }, [activeChatId]);

  useEffect(() => {
    setMessages([]);
    fetchMessages();
  }, [activeChatId, fetchMessages]);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Auto-resize input textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [inputText]);

  // Generate a clean title from the user's first prompt (like ChatGPT)
  const generateTitle = (prompt) => {
    const cleaned = prompt.trim().replace(/\s+/g, ' ');
    // Truncate to 50 chars and add ellipsis if needed
    if (cleaned.length <= 50) return cleaned;
    return cleaned.substring(0, 47) + '...';
  };

  const handleSend = async (e) => {
    if (e) e.preventDefault();
    if (!inputText.trim() || !activeRepoId || !activeChatId || loading) return;

    const userPrompt = inputText.trim();
    setInputText('');

    // Add user message locally immediately
    const newUserMsg = {
      message_id: `user-${Date.now()}`,
      role: 'user',
      content: userPrompt,
      created_at: new Date().toISOString()
    };
    setMessages(prev => [...prev, newUserMsg]);
    setLoading(true);

    // Auto-rename chat title on first message (like ChatGPT)
    const isFirstMessage = !titleSetRef.current;
    if (isFirstMessage) {
      titleSetRef.current = true;
      const title = generateTitle(userPrompt);
      try {
        await chatAPI.updateTitle(activeChatId, title);
        // Refresh sidebar so the new title shows immediately
        setRefreshTrigger(prev => prev + 1);
      } catch (err) {
        console.error('Failed to auto-update chat title:', err);
        // Non-fatal — don't block the query
      }
    }

    try {
      const data = await chatAPI.query(activeRepoId, activeChatId, userPrompt);

      const assistantMsg = {
        message_id: `ai-${Date.now()}`,
        role: 'assistant',
        content: `I searched the vector database for relevant code structures matching your query. Here are the top retrieved matching snippets from the repository:`,
        chunks: data.chunks || [],
        created_at: new Date().toISOString()
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (err) {
      console.error('Failed to run query:', err);
      const errorMsg = {
        message_id: `error-${Date.now()}`,
        role: 'assistant',
        content: `Error: ${err.response?.data?.detail || 'Failed to complete query. Please ensure the backend is running.'}`,
        isError: true,
        created_at: new Date().toISOString()
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const copyToClipboard = (text, idx) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(idx);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const formatFilePath = (path) => {
    if (!path) return '';
    const match = path.match(/(?:repo_[^\\/]+)[\\\/](.+)$/);
    if (match && match[1]) return match[1].replace(/\\/g, '/');
    const parts = path.split(/[\\\/]/);
    const repoIndex = parts.findIndex(p => p.startsWith('repo_'));
    if (repoIndex !== -1 && repoIndex + 1 < parts.length) {
      return parts.slice(repoIndex + 1).join('/');
    }
    return path;
  };

  // Handle creating a new chat session
  const handleCreateNewChat = async () => {
    if (creatingChat) return;
    setCreatingChat(true);
    try {
      const res = await chatAPI.newChat(activeRepoId);
      setActiveChatId(res.chat_id);
      setRefreshTrigger(prev => prev + 1);
    } catch (err) {
      console.error('Failed to start chat:', err);
      alert(err.response?.data?.detail || 'Failed to start a new chat session.');
    } finally {
      setCreatingChat(false);
    }
  };

  // ── Welcome screen: No repo selected ──
  if (!activeRepoId) {
    return (
      <div className="welcome-screen fade-in">
        <div className="welcome-logo">
          <Code size={48} />
        </div>
        <h1 className="welcome-title">Legacy Code RAG Assistant</h1>
        <p className="welcome-subtitle">
          Select an existing indexed repository from the sidebar or click below to upload a new public GitHub link to parse and search code structures.
        </p>
        <button className="auth-btn" onClick={onOpenUploadModal}>
          <Plus size={16} />
          <span>Index New Repository</span>
        </button>
      </div>
    );
  }

  // ── No chat selected: show prompt to create one ──
  if (!activeChatId) {
    return (
      <div className="welcome-screen fade-in">
        <div className="welcome-logo" style={{ color: 'var(--text-muted)' }}>
          <MessageSquare size={48} />
        </div>
        <h1 className="welcome-title">Start a Chat Session</h1>
        <p className="welcome-subtitle">
          Create a new session under this repository to ask structural questions and retrieve code elements.
        </p>
        <button
          className="auth-btn"
          onClick={handleCreateNewChat}
          disabled={creatingChat}
        >
          {creatingChat ? (
            <>
              <Loader2 size={16} className="spinner" />
              <span>Creating Session...</span>
            </>
          ) : (
            <>
              <Plus size={16} />
              <span>New Chat Session</span>
            </>
          )}
        </button>
      </div>
    );
  }

  // ── Active chat: message view ──
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', width: '100%' }}>
      {/* Scrollable message window */}
      <div className="chat-scroll-container">
        <div className="chat-message-list">

          {/* Empty state */}
          {messages.length === 0 && !loading && (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '40px 20px',
                color: 'var(--text-muted)',
                textAlign: 'center',
                border: '1px dashed var(--border-color)',
                borderRadius: '12px',
                marginTop: '40px'
              }}
            >
              <HelpCircle size={32} style={{ marginBottom: '12px' }} />
              <h3 style={{ marginBottom: '6px', color: 'var(--text-secondary)' }}>Ready to Query</h3>
              <p style={{ fontSize: '13px', maxWidth: '400px' }}>
                Ask questions about classes, methods, or logic structures in this repository.
                The RAG engine will fetch matching modules from ChromaDB.
              </p>
            </div>
          )}

          {/* Message list */}
          {messages.map((msg, index) => {
            const isUser = msg.role === 'user';

            return (
              <div
                key={msg.message_id || index}
                className={`message-row ${isUser ? 'user' : 'assistant'}`}
              >
                {/* Avatar */}
                <div className="message-avatar">
                  {isUser ? (user?.email || 'U').substring(0, 1).toUpperCase() : 'AI'}
                </div>

                {/* Bubble */}
                <div className="message-bubble">
                  <div className="message-sender">
                    {isUser ? 'You' : 'Assistant'}
                  </div>

                  <div className={`message-content-box${msg.isError ? ' error' : ''}`}>
                    {msg.content}
                  </div>

                  {/* Code chunks (assistant only) */}
                  {msg.chunks && msg.chunks.length > 0 && (
                    <div className="chunks-results-container" style={{ width: '100%' }}>
                      <div className="chunks-headline">
                        <Database size={13} />
                        <span>Retrieved Code Elements ({msg.chunks.length})</span>
                      </div>

                      {msg.chunks.map((chunk, cIdx) => {
                        const keyId = `${index}-${cIdx}`;
                        const cleanPath = formatFilePath(chunk.metadata?.file_path);
                        const funcName = chunk.metadata?.qualified_name || chunk.metadata?.function_name || 'Module Level';
                        const lineInfo = chunk.metadata?.start_line ? `L${chunk.metadata.start_line}-${chunk.metadata.end_line}` : '';
                        const similarity = Math.max(0, Math.round((1 - chunk.distance) * 100));

                        return (
                          <div key={keyId} className="chunk-card fade-in">
                            <div className="chunk-header">
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                                <FileCode size={14} style={{ color: 'var(--accent-green)', flexShrink: 0 }} />
                                <span className="chunk-file-path" title={chunk.metadata?.file_path}>
                                  {cleanPath} {lineInfo && `(${lineInfo})`}
                                </span>
                              </div>
                              <div className="chunk-meta-info">
                                <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{funcName}</span>
                                <span className="chunk-distance">Score: {similarity}%</span>
                              </div>
                            </div>
                            <div className="chunk-body">
                              <pre className="chunk-code">
                                <code>{chunk.text}</code>
                              </pre>
                              <button
                                className="chunk-copy-btn"
                                onClick={() => copyToClipboard(chunk.text, keyId)}
                                title="Copy code snippet"
                              >
                                {copiedIndex === keyId
                                  ? <Check size={14} style={{ color: '#10a37f' }} />
                                  : <Copy size={14} />
                                }
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {/* Typing / loading indicator */}
          {loading && (
            <div className="message-row assistant">
              <div className="message-avatar">AI</div>
              <div className="message-bubble">
                <div className="message-sender">Assistant</div>
                <div className="message-content-box" style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--text-muted)' }}>
                  <Loader2 size={15} className="spinner" />
                  <span style={{ fontSize: '14px' }}>Searching vector database for matching code snippets...</span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input area */}
      <div className="chat-input-container">
        <div className="chat-input-bar">
          <form onSubmit={handleSend} style={{ width: '100%' }}>
            <div className="chat-input-row">
              <button
                type="button"
                className="icon-btn"
                title="Index New Repository"
                onClick={onOpenUploadModal}
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '50%',
                  backgroundColor: 'var(--bg-tertiary)',
                  border: '1px solid var(--border-color)',
                  color: 'var(--text-primary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: '2px',
                  flexShrink: 0
                }}
              >
                <Plus size={18} />
              </button>

              <textarea
                ref={textareaRef}
                className="chat-textarea"
                rows={1}
                placeholder="Ask about classes, functions, or specific code details..."
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={loading}
              />

              <button
                type="submit"
                className="chat-submit-btn"
                disabled={loading || !inputText.trim()}
              >
                <Send size={16} />
              </button>
            </div>
          </form>
          <div className="chat-input-footer-text">
            Legacy Code RAG uses ChromaDB similarity matching. Always inspect returned snippets.
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatArea;
