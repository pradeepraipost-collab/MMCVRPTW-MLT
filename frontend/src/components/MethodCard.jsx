// MethodCard — one entry in the 10-method picker grid (spec §7.5.B).
//
// Card layout: badge, name (Syne), tagline, solve-time + gap pills, 4 bullets,
// Select button. Active state uses teal-glow; disabled (roadmap) is 0.55 opacity.

import { Check, X } from 'lucide-react'

const BADGE_PALETTE = {
  amber:  { bg: 'rgba(251,191,36,0.12)',  fg: '#fbbf24', border: 'rgba(251,191,36,0.3)' },
  teal:   { bg: 'rgba(13,148,136,0.12)',  fg: '#2dd4bf', border: 'rgba(13,148,136,0.3)' },
  purple: { bg: 'rgba(168,85,247,0.12)',  fg: '#c084fc', border: 'rgba(168,85,247,0.3)' },
  blue:   { bg: 'rgba(59,130,246,0.12)',  fg: '#60a5fa', border: 'rgba(59,130,246,0.3)' },
  slate:  { bg: 'rgba(148,163,184,0.08)', fg: '#94a3b8', border: 'rgba(148,163,184,0.2)' },
}

export default function MethodCard({ method, selected, onSelect }) {
  const palette = BADGE_PALETTE[method.badgeColor] || BADGE_PALETTE.teal
  const disabled = !method.enabled

  return (
    <div
      className={`glass-panel rounded-2xl p-5 transition-all duration-200 ${
        selected ? 'teal-glow' : 'glass-panel-hover'
      }`}
      style={{
        opacity: disabled ? 0.55 : 1,
        border: selected
          ? '1px solid rgba(13,148,136,0.5)'
          : '1px solid var(--border-subtle)',
        cursor: disabled ? 'not-allowed' : 'pointer',
      }}
      onClick={() => !disabled && onSelect(method.id)}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <span
          className="text-[10px] font-bold tracking-widest px-2 py-0.5 rounded border"
          style={{ background: palette.bg, color: palette.fg, borderColor: palette.border }}
        >
          {method.badge}
        </span>
        {selected && (
          <span className="text-[10px] font-bold text-emerald-400 tracking-widest">SELECTED</span>
        )}
      </div>

      <h3 style={{ fontFamily: 'Syne, sans-serif', fontSize: '14.5px', fontWeight: 700, color: '#f0f4f8', letterSpacing: '-0.01em' }}>
        {method.name}
      </h3>
      <p className="text-xs text-slate-400 mt-1 mb-3">{method.tagline}</p>

      <div className="flex gap-2 mb-3">
        <Pill label="Solve time" value={method.solveTime} />
        <Pill label="Gap" value={method.gap} />
      </div>

      <ul className="space-y-1.5 mb-4">
        {method.bullets.map((b, i) => (
          <li key={i} className="flex items-start gap-2 text-[11.5px] text-slate-300">
            {b.ok
              ? <Check size={12} className="mt-0.5 flex-shrink-0 text-emerald-400" />
              : <X size={12} className="mt-0.5 flex-shrink-0 text-rose-400" />}
            <span>{b.text}</span>
          </li>
        ))}
      </ul>

      <button
        disabled={disabled}
        onClick={(e) => { e.stopPropagation(); !disabled && onSelect(method.id) }}
        className={`w-full px-3 py-2 rounded-lg text-xs font-bold transition-all ${
          disabled
            ? 'text-slate-700 cursor-not-allowed'
            : selected
              ? 'btn-teal text-white'
              : 'border border-teal-700/40 text-teal-300 hover:bg-teal-900/20'
        }`}
        style={disabled ? { background: 'rgba(255,255,255,0.02)' } : undefined}
      >
        {disabled ? 'Phase 2 — disabled' : selected ? 'Selected' : 'Select'}
      </button>
    </div>
  )
}

function Pill({ label, value }) {
  return (
    <div className="flex-1 rounded-md px-2 py-1.5"
      style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)' }}>
      <p className="text-[9px] uppercase font-bold tracking-widest text-slate-500">{label}</p>
      <p className="text-[11px] font-semibold text-slate-200">{value}</p>
    </div>
  )
}
