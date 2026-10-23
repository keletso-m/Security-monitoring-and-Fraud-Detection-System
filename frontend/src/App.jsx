import React, { useState } from 'react';
import Overview from './components/Overview';
import Incidents from './components/Incidents';

const NAV = [
  { id: 'overview',  label: 'Overview',     icon: '▦' },
  { id: 'incidents', label: 'Incidents',     icon: '≡' },
];

export default function App() {
  const [page, setPage] = useState('overview');

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: 'var(--bg)' }}>

      {/* Sidebar */}
      <div style={{
        width: 200, background: '#0d1014',
        borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column',
        padding: '16px 0', flexShrink: 0,
      }}>
        {/* Logo */}
        <div style={{
          padding: '0 16px 24px',
          fontSize: 15, fontWeight: 700,
          letterSpacing: '0.06em',
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%',
            background: 'var(--accent)',
            boxShadow: '0 0 8px var(--accent)',
          }} />
          SENTINEL
        </div>

        {/* Nav */}
        {NAV.map(item => (
          <button
            key={item.id}
            onClick={() => setPage(item.id)}
            style={{
              padding: '9px 16px',
              display: 'flex', alignItems: 'center', gap: 10,
              fontSize: 13, fontWeight: 500,
              color: page === item.id ? 'var(--text)' : 'var(--muted)',
              background: page === item.id ? 'rgba(59,130,246,0.08)' : 'transparent',
              borderRight: page === item.id ? '2px solid var(--accent)' : '2px solid transparent',
              cursor: 'pointer', textAlign: 'left', width: '100%',
              transition: 'all 0.1s',
            }}
          >
            <span style={{ fontSize: 14, opacity: 0.7 }}>{item.icon}</span>
            {item.label}
          </button>
        ))}

        {/* Status */}
        <div style={{
          marginTop: 'auto', padding: '12px 16px',
          borderTop: '1px solid var(--border)',
        }}>
          <div style={{ fontSize: 10, color: 'var(--faint)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 4 }}>
            API
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--low)', fontFamily: 'var(--font-mono)' }}>
            <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--low)', animation: 'pulse 1.5s infinite' }} />
            localhost:8000
          </div>
        </div>

        <style>{`
          @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.3; } }
        `}</style>
      </div>

      {/* Main */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* Topbar */}
        <div style={{
          height: 50, borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 24px', flexShrink: 0,
        }}>
          <span style={{ fontSize: 13, fontWeight: 500 }}>
            {NAV.find(n => n.id === page)?.label}
          </span>
          <span style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'var(--font-mono)' }}>
            auto-refresh 10s
          </span>
        </div>

        {/* Page content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
          {page === 'overview'  && <Overview  onNavigate={setPage} />}
          {page === 'incidents' && <Incidents />}
        </div>
      </div>
    </div>
  );
}