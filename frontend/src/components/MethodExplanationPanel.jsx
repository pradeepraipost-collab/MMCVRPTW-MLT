// MethodExplanationPanel — appears below the method grid when one is selected.
// Layout per spec §7.5.D:
//   - 4-cell spec row at top
//   - 2-column "solves" / "does NOT solve" block
//   - 4-step algorithm card grid
//   - Blue info box: "About the gap claim"

import { Check, X, Info } from 'lucide-react'

export default function MethodExplanationPanel({ method }) {
  if (!method) return null
  const d = method.detail

  return (
    <div className="glass-panel rounded-2xl p-6 fade-in-up">
      {/* 4-cell spec row */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        <SpecCell label="Expected solve"   value={method.solveTime} />
        <SpecCell label="Confirmed gap"    value={method.gap} />
        <SpecCell label="Sub-problems"     value={String(d.subproblems)} />
        <SpecCell label="Parallelism"      value={d.parallelism} />
      </div>

      {/* Two-column solves / does NOT solve */}
      <div className="grid grid-cols-2 gap-6 mb-6">
        <div>
          <p className="text-[10px] uppercase font-bold tracking-widest text-emerald-400 mb-2">
            What this method solves
          </p>
          <ul className="space-y-2">
            {d.solves.map((s, i) => (
              <li key={i} className="flex gap-2 text-[12.5px] text-slate-300">
                <Check size={14} className="mt-0.5 flex-shrink-0 text-emerald-400" />
                <span>{s}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-[10px] uppercase font-bold tracking-widest text-rose-400 mb-2">
            What it does NOT solve
          </p>
          <ul className="space-y-2">
            {d.doesNotSolve.map((s, i) => (
              <li key={i} className="flex gap-2 text-[12.5px] text-slate-300">
                <X size={14} className="mt-0.5 flex-shrink-0 text-rose-400" />
                <span>{s}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* 4-step algorithm card grid */}
      <p className="text-[10px] uppercase font-bold tracking-widest text-slate-500 mb-2">
        Algorithm
      </p>
      <div className="grid grid-cols-4 gap-3 mb-6">
        {d.algorithm.map((s, i) => (
          <div key={i} className="rounded-xl p-4"
            style={{ background: 'rgba(13,148,136,0.04)', border: '1px solid rgba(13,148,136,0.12)' }}>
            <p className="text-[9px] font-bold tracking-widest text-teal-400 uppercase mb-1">
              Step {i + 1}
            </p>
            <p style={{ fontFamily: 'Syne, sans-serif', fontSize: '13px', fontWeight: 700, color: '#f0f4f8' }}>
              {s.step}
            </p>
            <p className="text-[11.5px] text-slate-400 mt-1.5 leading-snug">{s.desc}</p>
          </div>
        ))}
      </div>

      {/* Blue info box: gap claim */}
      <div className="rounded-xl p-4 flex gap-3"
        style={{ background: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.2)' }}>
        <Info size={16} className="text-blue-400 flex-shrink-0 mt-0.5" />
        <div>
          <p className="text-[10px] uppercase font-bold tracking-widest text-blue-400 mb-1">
            About the gap claim
          </p>
          <p className="text-[12.5px] text-slate-300 leading-snug">{d.bound}</p>
        </div>
      </div>
    </div>
  )
}

function SpecCell({ label, value }) {
  return (
    <div className="rounded-xl px-4 py-3"
      style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
      <p className="text-[9px] uppercase font-bold tracking-widest text-slate-500 mb-1">{label}</p>
      <p style={{ fontFamily: 'Syne, sans-serif', fontSize: '13.5px', fontWeight: 600, color: '#f0f4f8' }}>
        {value}
      </p>
    </div>
  )
}
