import React, { useState, useEffect } from 'react';
import { uploadAPI } from '../services/api';
import { GitBranch, AlertTriangle, ArrowRight, Loader2, CheckCircle2 } from 'lucide-react';

const RepoUpload = ({ onUploadSuccess }) => {
  const [repoUrl, setRepoUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  
  // Progress state
  const [jobId, setJobId] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null); // pending | cloning | parsing | embedding | storing | ready | failed
  const [chunksDone, setChunksDone] = useState(0);
  const [totalChunks, setTotalChunks] = useState(0);

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!repoUrl) return;

    // Simple GitHub validation
    if (!repoUrl.includes('github.com')) {
      setError('Please enter a valid GitHub repository URL.');
      return;
    }

    setError('');
    setLoading(true);
    try {
      const data = await uploadAPI.uploadRepo(repoUrl);
      setJobId(data.job_id);
      setSessionId(data.session_id);
      setJobStatus(data.status || 'pending');
    } catch (err) {
      console.error(err);
      setError(err.response?.data?.detail || 'Failed to start repository indexing.');
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!jobId) return;

    let pollInterval = setInterval(async () => {
      try {
        const data = await uploadAPI.getStatus(jobId);
        setJobStatus(data.status);
        setChunksDone(data.chunks_done || 0);
        setTotalChunks(data.total_chunks || 0);

        if (data.status === 'ready') {
          clearInterval(pollInterval);
          setLoading(false);
          // Wait 1.5s for user to see the success state
          setTimeout(() => {
            onUploadSuccess(sessionId);
            // Reset
            setJobId(null);
            setSessionId(null);
            setJobStatus(null);
            setRepoUrl('');
          }, 1500);
        } else if (data.status === 'failed') {
          clearInterval(pollInterval);
          setError(data.error || 'Indexing failed.');
          setLoading(false);
          setJobId(null);
        }
      } catch (err) {
        console.error('Polling error:', err);
        // Do not fail immediately, let it retry
      }
    }, 2000);

    return () => clearInterval(pollInterval);
  }, [jobId, sessionId]);

  // Calculate percentages
  const getProgressPercentage = () => {
    if (jobStatus === 'ready') return 100;
    if (jobStatus === 'storing') return 90;
    if (jobStatus === 'embedding') {
      if (totalChunks === 0) return 60;
      return Math.min(85, Math.floor(40 + (chunksDone / totalChunks) * 45));
    }
    if (jobStatus === 'parsing') return 30;
    if (jobStatus === 'cloning') return 15;
    if (jobStatus === 'pending') return 5;
    return 0;
  };

  const steps = [
    { key: 'cloning', label: 'Cloning Repository' },
    { key: 'parsing', label: 'Parsing Source Files' },
    { key: 'embedding', label: 'Generating Code Embeddings' },
    { key: 'storing', label: 'Saving to ChromaDB Vector Store' },
  ];

  const getStepStatus = (stepKey, index) => {
    const statusOrder = ['pending', 'cloning', 'parsing', 'embedding', 'storing', 'ready', 'failed'];
    const currentIdx = statusOrder.indexOf(jobStatus);
    
    // Find the relative order of steps
    const stepIdx = statusOrder.indexOf(stepKey);

    if (jobStatus === 'failed') {
      if (currentIdx === stepIdx) return 'failed';
    }

    if (currentIdx > stepIdx) return 'complete';
    if (currentIdx === stepIdx) return 'active';
    return 'upcoming';
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: '100%' }}>
      {!jobId ? (
        <div className="upload-card fade-in">
          <h2 className="upload-title">Connect your codebase</h2>
          <p className="upload-subtitle">
            Provide a public GitHub repository link. We will clone, parse, and index the code structures into a vector store for questioning.
          </p>
          
          {error && (
            <div className="error-banner" style={{ margin: '0 0 16px 0' }}>
              <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleUpload}>
            <div className="upload-form-row">
              <div className="upload-input-wrap">
                <GitBranch size={18} className="upload-input-icon" />
                <input
                  type="url"
                  className="upload-input"
                  placeholder="https://github.com/username/repository"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  disabled={loading}
                  required
                />
              </div>
              <button type="submit" className="upload-btn" disabled={loading || !repoUrl}>
                {loading ? <Loader2 size={16} className="spinner" /> : <ArrowRight size={16} />}
                <span>Index Repo</span>
              </button>
            </div>
          </form>
        </div>
      ) : (
        <div className="progress-card fade-in">
          <div className="progress-header">
            <div className="progress-title">
              {jobStatus === 'ready' ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent-green)' }}>
                  <CheckCircle2 size={18} />
                  <span>Repository Ready!</span>
                </div>
              ) : (
                <span>Indexing Codebase...</span>
              )}
            </div>
            <div className="progress-pct">{getProgressPercentage()}%</div>
          </div>

          <div className="progress-bar-bg">
            <div 
              className="progress-bar-fill" 
              style={{ width: `${getProgressPercentage()}%` }} 
            />
          </div>

          <div className="progress-steps">
            {steps.map((step, idx) => {
              const status = getStepStatus(step.key, idx);
              return (
                <div 
                  key={step.key} 
                  className={`progress-step-row ${status === 'active' ? 'step-row-active' : ''} ${status === 'complete' ? 'step-row-complete' : ''}`}
                >
                  <div className="step-label">
                    {status === 'complete' && (
                      <span className="step-icon-check"><CheckCircle2 size={16} /></span>
                    )}
                    {status === 'active' && <span className="spinner" />}
                    {status === 'upcoming' && (
                      <div 
                        style={{
                          width: '16px',
                          height: '16px',
                          borderRadius: '50%',
                          border: '2px solid var(--border-color)',
                          display: 'inline-block'
                        }} 
                      />
                    )}
                    {status === 'failed' && (
                      <span style={{ color: 'var(--accent-danger)' }}><AlertTriangle size={16} /></span>
                    )}
                    <span>{step.label}</span>
                  </div>
                  
                  <div className="step-status">
                    {status === 'complete' && 'Completed'}
                    {status === 'active' && (
                      <>
                        {step.key === 'embedding' && totalChunks > 0 ? (
                          `Processing chunks (${chunksDone}/${totalChunks})`
                        ) : (
                          'In Progress...'
                        )}
                      </>
                    )}
                    {status === 'upcoming' && 'Waiting'}
                    {status === 'failed' && 'Failed'}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export default RepoUpload;
