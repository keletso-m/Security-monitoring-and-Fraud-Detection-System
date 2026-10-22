import React, { useEffect, useState, useCallback } from 'react';
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import { api } from '../api';
import { AlertBadge, ScoreBar, Card, StatCard, SectionHeader, Spinner } from './ui';
import { format, parseISO, subHours, isAfter } from 'date-fns';

const LEVEL_COLOR = { LOW: '#22c55e', MEDIUM: '#eab308', HIGH: '#f97316', CRITICAL: '#ef4444' };

function buildTimelineBuckets(incidents) {
  const now = new Date();
  const buckets = Array.from({ length: 12 }, (_, i) => {
    const t = subHours(now, 11 - i);
    return { label: format(t, 'HH:mm'), count: 0, score: 0, n: 0 };
  });
  incidents.forEach(inc => {
    const ts = parseISO(inc.timestamp);
    const bucket = buckets.findIndex((_, i) => {
      const from = subHours(now, 11 - i);
      const to   = subHours(now, 10 - i);
      return isAfter(ts, from) && !isAfter(ts, to);
    });
    if (bucket >= 0) {
      buckets[bucket].count++;
      buckets[bucket].score += inc.risk_score;
      buckets[bucket].n++;
    }
  });
  return buckets.map(b => ({ ...b, avg_score: b.n ? Math.round(b.score / b.n) : 0 }));
}

function buildLevelDist(incidents) {
  const counts = { LOW: 0, MEDIUM: 0, HIGH: 0, CRITICAL: 0 };
  incidents.forEach(i => { if (counts[i.alert_level] !== undefined) counts[i.alert_level]++; });
  return Object.entries(counts).map(([level, count]) => ({ level, count }));
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: '#1a1f28', border: '1px solid var(--border-em)', borderRadius: 6, padding: '8px 12px', fontSize: 12 }}>
      <p style={{ color: 'var(--muted)', marginBottom: 4 }}>{label}</p>
      {payload.map(p => (
        <p key={p.name} style={{ color: p.color || 'var(--text)' }}>{p.name}: <strong>{p.value}</strong></p>
      ))}
    </div>
  );
};

export default function Overview({ onNavigate }) {
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading]     = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await api.getIncidents({ limit: 200 });
      setIncidents(Array.isArray(data) ? data : data.incidents || []);
    } catch (_) {}
    setLoading(false);
  }, []);

  useEffect(() => { load(); const t = setInterval(load, 4000); return () => clearInterval(t); }, [load]);

  if (loading) return <Spinner />;

  const total     = incidents.length;
  const critical  = incidents.filter(i => i.alert_level === 'CRITICAL').length;
  const high      = incidents.filter(i => i.alert_level === 'HIGH').length;
  const avgScore  = total ? Math.round(incidents.reduce((s, i) => s + i.risk_score, 0) / total) : 0;
  const recent24  = incidents.filter(i => isAfter(parseISO(i.timestamp), subHours(new Date(), 24))).length;

  const timeline  = buildTimelineBuckets(incidents);
  const levelDist = buildLevelDist(incidents);
  const recent    = [...incidents].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)).slice(0, 8);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
        <StatCard label="Total incidents" value={total} />
        <StatCard label="Last 24 h"       value={recent24} sub="new events" accent="var(--accent)" />
        <StatCard label="Critical"         value={critical} accent="#ef4444" />
        <StatCard label="High"             value={high}     accent="#f97316" />
        <StatCard label="Avg risk score"   value={avgScore} sub="out of 100" accent={avgScore >= 75 ? '#ef4444' : avgScore >= 50 ? '#f97316' : '#eab308'} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 16 }}>
        <Card>
          <SectionHeader title="Events — last 12 hours" />
          <div style={{ height: 180 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timeline} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                <defs>
                  <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}    />
                  </linearGradient>
                </defs>
                <XAxis dataKey="label" tick={{ fill: '#7a8494', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#7a8494', fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip content={<CustomTooltip />} />
                <Area type="monotone" dataKey="count" name="Events" stroke="#3b82f6" fill="url(#grad)" strokeWidth={2} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <SectionHeader title="By level" />
          <div style={{ height: 180 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={levelDist} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                <XAxis dataKey="level" tick={{ fill: '#7a8494', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#7a8494', fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" name="Count" radius={[3, 3, 0, 0]}>
                  {levelDist.map(entry => (
                    <Cell key={entry.level} fill={LEVEL_COLOR[entry.level]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <Card>
        <SectionHeader
          title="Recent incidents"
          action={<button onClick={() => onNavigate('incidents')} style={{ fontSize: 12, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer' }}>View all →</button>}
        />
        {recent.length === 0 ? (
          <p style={{ color: 'var(--muted)', fontSize: 13 }}>No incidents yet. Submit an event to get started.</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['ID', 'Type', 'Level', 'Score', 'Flags', 'Time'].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '6px 10px', color: 'var(--muted)', fontWeight: 500, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recent.map(inc => (
                <tr key={inc.id} style={{ borderBottom: '1px solid var(--border)', transition: 'background 0.1s' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-hover)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <td style={{ padding: '10px 10px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--muted)' }}>#{inc.id}</td>
                  <td style={{ padding: '10px 10px', fontFamily: 'var(--font-mono)', fontSize: 11 }}>{inc.event_type}</td>
                  <td style={{ padding: '10px 10px' }}><AlertBadge level={inc.alert_level} /></td>
                  <td style={{ padding: '10px 10px', width: 120 }}><ScoreBar score={inc.risk_score} /></td>
                  <td style={{ padding: '10px 10px', color: 'var(--muted)', fontSize: 11, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {(inc.reason_flags || []).join(', ')}
                  </td>
                  <td style={{ padding: '10px 10px', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--muted)', whiteSpace: 'nowrap' }}>
                    {format(parseISO(inc.timestamp), 'HH:mm:ss')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}