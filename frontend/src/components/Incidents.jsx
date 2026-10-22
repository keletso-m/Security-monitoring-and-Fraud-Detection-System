import React, { useEffect, useState, useCallback } from 'react';
import { api } from '../api';
import { AlertBadge, ScoreBar, Card, SectionHeader, Spinner, Btn } from './ui';
import { format, parseISO } from 'date-fns';

const LEVELS = ['ALL', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];
const TYPES  = ['ALL', 'activity', 'transaction'];

export default function Incidents() {
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading]     = useState(true);
  const [selected, setSelected]   = useState(null);
  const [levelFilter, setLevel]   = useState('ALL');
  const [typeFilter, setType]     = useState('ALL');
  const [search, setSearch]       = useState('');
  const [page, setPage]           = useState(0);
  const PAGE_SIZE = 20;

  const load = useCallback(async () => {
    try {
      const data = await api.getIncidents({ limit: 500 });
      setIncidents(Array.isArray(data) ? data : data.incidents || []);
    } catch (_) {}
    setLoading(false);
  }, []);

  useEffect(() => { load(); const t = setInterval(load, 4000); return () => clearInterval(t); }, [load]);

  const filtered = incidents
    .filter(i => levelFilter === 'ALL' || i.alert_level === levelFilter)
    .filter(i => typeFilter  === 'ALL' || i.event_type  === typeFilter)
    .filter(i => {
      if (!search) return true;
      const q = search.toLowerCase();
      return (
        String(i.id).includes(q) ||
        (i.event_type || '').toLowerCase().includes(q) ||
        (i.reason_flags || []).join(' ').toLowerCase().includes(q)
      );
    })
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

  const pages = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <Card>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            placeholder="Search by ID, type, flags…"
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(0); }}
            style={{ width: 240 }}
          />
          <div style={{ display: 'flex', gap: 4 }}>
            {LEVELS.map(l => (
              <button key={l} onClick={() => { setLevel(l); setPage(0); }} style={{
                padding: '5px 10px', borderRadius: 4, fontSize: 11, fontFamily: 'var(--font-mono)',
                background: levelFilter === l ? 'var(--accent)' : 'var(--bg-hover)',
                color: levelFilter === l ? '#fff' : 'var(--muted)',
                border: '1px solid var(--border-em)', cursor: 'pointer',
              }}>{l}</button>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 4 }}>
            {TYPES.map(t => (
              <button key={t} onClick={() => { setType(t); setPage(0); }} style={{
                padding: '5px 10px', borderRadius: 4, fontSize: 11, fontFamily: 'var(--font-mono)',
                background: typeFilter === t ? 'rgba(59,130,246,0.2)' : 'var(--bg-hover)',
                color: typeFilter === t ? 'var(--accent)' : 'var(--muted)',
                border: '1px solid var(--border-em)', cursor: 'pointer',
              }}>{t}</button>
            ))}
          </div>
          <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--muted)', fontFamily: 'var(--font-mono)' }}>
            {filtered.length} results
          </span>
          <Btn onClick={load}>Refresh</Btn>
        </div>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: selected ? '1fr 360px' : '1fr', gap: 16 }}>
        <Card style={{ padding: 0, overflow: 'hidden' }}>
          {loading ? <Spinner /> : paged.length === 0 ? (
            <p style={{ padding: '2rem', color: 'var(--muted)', textAlign: 'center', fontSize: 13 }}>No incidents match your filters.</p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['ID', 'Type', 'Level', 'Score', 'Flags', 'Timestamp'].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '10px 14px', color: 'var(--muted)', fontWeight: 500, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {paged.map(inc => (
                  <tr key={inc.id}
                    onClick={() => setSelected(inc.id === selected?.id ? null : inc)}
                    style={{
                      borderBottom: '1px solid var(--border)',
                      cursor: 'pointer',
                      background: selected?.id === inc.id ? 'var(--accent-dim)' : 'transparent',
                      transition: 'background 0.1s',
                    }}
                    onMouseEnter={e => { if (selected?.id !== inc.id) e.currentTarget.style.background = 'var(--bg-hover)'; }}
                    onMouseLeave={e => { if (selected?.id !== inc.id) e.currentTarget.style.background = 'transparent'; }}
                  >
                    <td style={{ padding: '10px 14px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--muted)' }}>#{inc.id}</td>
                    <td style={{ padding: '10px 14px', fontFamily: 'var(--font-mono)', fontSize: 11 }}>{inc.event_type}</td>
                    <td style={{ padding: '10px 14px' }}><AlertBadge level={inc.alert_level} /></td>
                    <td style={{ padding: '10px 14px', width: 130 }}><ScoreBar score={inc.risk_score} /></td>
                    <td style={{ padding: '10px 14px', color: 'var(--muted)', fontSize: 11, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {(inc.reason_flags || []).join(', ')}
                    </td>
                    <td style={{ padding: '10px 14px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--muted)', whiteSpace: 'nowrap' }}>
                      {format(parseISO(inc.timestamp), 'dd MMM HH:mm:ss')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {pages > 1 && (
            <div style={{ display: 'flex', gap: 6, padding: '12px 14px', borderTop: '1px solid var(--border)', alignItems: 'center' }}>
              <Btn onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}>← Prev</Btn>
              <span style={{ fontSize: 12, color: 'var(--muted)', fontFamily: 'var(--font-mono)' }}>
                {page + 1} / {pages}
              </span>
              <Btn onClick={() => setPage(p => Math.min(pages - 1, p + 1))} disabled={page === pages - 1}>Next →</Btn>
            </div>
          )}
        </Card>

        {selected && <IncidentDetail incident={selected} onClose={() => setSelected(null)} />}
      </div>
    </div>
  );
}

function IncidentDetail({ incident: inc, onClose }) {
  return (
    <Card style={{ position: 'sticky', top: 80, alignSelf: 'start' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--muted)' }}>Incident #{inc.id}</span>
        <button onClick={onClose} style={{ color: 'var(--muted)', fontSize: 16, cursor: 'pointer', background: 'none', border: 'none' }}>✕</button>
      </div>

      <div style={{ marginBottom: 12 }}><AlertBadge level={inc.alert_level} /></div>

      <div style={{ marginBottom: 16 }}>
        <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>RISK SCORE</p>
        <ScoreBar score={inc.risk_score} />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13 }}>
        <Row label="Type"      value={inc.event_type} mono />
        <Row label="Timestamp" value={format(parseISO(inc.timestamp), 'dd MMM yyyy HH:mm:ss')} mono />

        {inc.reason_flags?.length > 0 && (
          <div>
            <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6 }}>REASON FLAGS</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {inc.reason_flags.map((f, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, fontFamily: 'var(--font-mono)', color: '#f97316' }}>
                  <span style={{ color: '#f97316', fontSize: 8 }}>▶</span> {f}
                </div>
              ))}
            </div>
          </div>
        )}

        {inc.raw_event && (
          <div>
            <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6 }}>RAW EVENT</p>
            <pre style={{
              background: 'var(--bg)', borderRadius: 4, padding: '10px 12px',
              fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--muted)',
              overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
              border: '1px solid var(--border)',
            }}>
              {JSON.stringify(inc.raw_event, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </Card>
  );
}

function Row({ label, value, mono }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
      <span style={{ color: 'var(--muted)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', flexShrink: 0 }}>{label}</span>
      <span style={{ fontFamily: mono ? 'var(--font-mono)' : 'inherit', fontSize: 12, textAlign: 'right', wordBreak: 'break-all' }}>{value}</span>
    </div>
  );
}