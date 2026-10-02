import React, { useState } from 'react';
import { authAPI } from '../services/api';
import { LogIn, UserPlus, AlertCircle, Eye, EyeOff } from 'lucide-react';

const Auth = ({ onAuthSuccess }) => {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (isLogin) {
        const data = await authAPI.login(email, password);
        onAuthSuccess(data.user);
      } else {
        const data = await authAPI.signup(email, password, fullName);
        onAuthSuccess(data.user);
      }
    } catch (err) {
      console.error(err);
      setError(
        err.response?.data?.detail || 
        'An authentication error occurred. Please verify your credentials.'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-background-mesh" />
      <div className="auth-card">
        <div className="auth-logo">
          <span>{`{ }`}</span> LegacyCodeRAG
        </div>
        <p className="auth-subtitle">
          {isLogin 
            ? 'Sign in to access your codebase assistant' 
            : 'Create an account to start indexing your repos'}
        </p>

        {error && (
          <div className="error-banner">
            <AlertCircle size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
            <span>{error}</span>
          </div>
        )}

        <form className="auth-form" onSubmit={handleSubmit}>
          {!isLogin && (
            <div className="form-group">
              <label className="form-label" htmlFor="fullName">Full Name</label>
              <input
                id="fullName"
                type="text"
                className="form-input"
                placeholder="John Doe"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required={!isLogin}
              />
            </div>
          )}

          <div className="form-group">
            <label className="form-label" htmlFor="email">Email Address</label>
            <input
              id="email"
              type="email"
              className="form-input"
              placeholder="name@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="password">Password</label>
            <div style={{ position: 'relative' }}>
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                className="form-input"
                style={{ paddingRight: '44px' }}
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
              />
              <button
                type="button"
                className="icon-btn"
                style={{
                  position: 'absolute',
                  right: '12px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                  padding: '2px',
                }}
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <button type="submit" className="auth-btn" disabled={loading}>
            {loading ? (
              <span className="spinner" />
            ) : isLogin ? (
              <>
                <LogIn size={16} />
                <span>Log In</span>
              </>
            ) : (
              <>
                <UserPlus size={16} />
                <span>Sign Up</span>
              </>
            )}
          </button>
        </form>

        <div className="auth-footer">
          {isLogin ? (
            <>
              Don't have an account?
              <button 
                type="button" 
                className="auth-link" 
                onClick={() => { setIsLogin(false); setError(''); }}
              >
                Sign Up
              </button>
            </>
          ) : (
            <>
              Already have an account?
              <button 
                type="button" 
                className="auth-link" 
                onClick={() => { setIsLogin(true); setError(''); }}
              >
                Log In
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default Auth;
