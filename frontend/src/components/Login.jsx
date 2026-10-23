import React, { useState } from 'react';
import { api } from '../api';
import { Card, Btn } from './ui';

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError]       = useState(null);
  const [loading, setLoading]   = useState(false);

  const submit = async () => {
    if (!username || !password) return;
    setLoading(true); setError(null);
    try {
      await api.login(username, password);
      onLogin();
    } catch (e) {
      setError(e.message);
      setLoading(false);
    }
  };

  const onKey = (e) => { if (e.key === 'Enter') submit(); };

  return (
    <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
      <Card style={{ width: 340 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 15, fontWeight: 700, letterSpacing: '0.06em', marginBottom: 18 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)', boxShadow: '0 0 8px var(--accent)' }} />
          SENTINEL
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <input placeholder="Username" value={username} onChange={e => setUsername(e.target.value)} onKeyDown={onKey} autoFocus />
          <input type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} onKeyDown={onKey} />
          {error && <p style={{ color: '#ef4444', fontSize: 12, fontFamily: 'var(--font-mono)' }}>{error}</p>}
          <Btn variant="primary" onClick={submit} disabled={loading}>{loading ? 'Signing in…' : 'Sign in'}</Btn>
        </div>
      </Card>
    </div>
  );
}
