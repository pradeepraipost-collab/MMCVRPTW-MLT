// Reusable KPI tile — Syne label, large value, teal-glow on hover.

export default function KpiCard({ label, value, sub, accent = 'teal' }) {
  const accentBg = {
    teal: 'rgba(13,148,136,0.12)',
    amber: 'rgba(251,191,36,0.12)',
    rose: 'rgba(244,63,94,0.12)',
    slate: 'rgba(148,163,184,0.1)',
  }[accent] || 'rgba(13,148,136,0.12)'
  return (
    <div className="glass-panel kpi-card rounded-2xl p-5">
      <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">{label}</p>
      <p style={{ fontFamily: 'Syne, sans-serif', fontSize: '28px', fontWeight: 700, color: '#f0f4f8', letterSpacing: '-0.02em' }}>
        {value}
      </p>
      {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
      <div className="mt-3 h-1 rounded-full" style={{ background: accentBg }} />
    </div>
  )
}
