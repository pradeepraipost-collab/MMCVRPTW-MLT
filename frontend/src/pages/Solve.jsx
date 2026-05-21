// Step 3 — live solver log via SSE. Elapsed timer + incumbent/bound/gap
// pills + progress bar + SolverLogConsole (with cancel) per spec §7.6.

import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Timer, Activity, Target, ArrowRight } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'
import SolverLogConsole from '../components/SolverLogConsole.jsx'

const TIME_CAP_SEC = 3600

export default function Solve() {
  const { solveStatus, solveLog, solveStats, cancelSolve, selectedMethodId } = useApp()
  const navigate = useNavigate()
  const [tick, setTick] = useState(0)

  // tick every second so the elapsed timer updates client-side between SSE frames
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000)
    return () => clearInterval(id)
  }, [])

  const elapsed = solveStats.elapsed_sec || 0
  const mm = Math.floor(elapsed / 60).toString().padStart(2, '0')
  const ss = Math.floor(elapsed % 60).toString().padStart(2, '0')
  const pct = useMemo(() => Math.min(100, (elapsed / TIME_CAP_SEC) * 100), [elapsed])

  return (
    <div className="max-w-6xl mx-auto fade-in-up">
      <p className="text-[10px] font-bold uppercase tracking-widest text-teal-400 mb-2">Step 3 · Solving</p>
      <h1 className="text-gradient-teal" style={{ fontFamily: 'Syne, sans-serif', fontSize: '32px', fontWeight: 700, letterSpacing: '-0.02em' }}>
        Method: {selectedMethodId || '—'}
      </h1>
      <p className="text-slate-400 mt-2 mb-6">
        Live HiGHS output streams below. Cancel any time — graceful stop within 5s on average
        (HiGHS doesn't expose mid-solve Python interrupts, so cancellation waits for the current
        MIP node to finish).
      </p>

      {/* Stats pills */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        <Pill icon={Timer} label="Elapsed" value={`${mm}:${ss}`} />
        <Pill icon={Activity} label="Incumbent" value={fmtInr(solveStats.incumbent)} />
        <Pill icon={Target} label="Best bound" value={fmtInr(solveStats.bound)} />
        <Pill icon={Target} label="Gap" value={solveStats.gap_pct != null ? `${solveStats.gap_pct.toFixed(2)}%` : '—'} />
      </div>

      {/* Progress bar */}
      <div className="mb-6">
        <div className="flex justify-between text-[10px] uppercase font-bold tracking-widest text-slate-500 mb-1">
          <span>Progress · 60-min cap</span>
          <span>{pct.toFixed(1)}%</span>
        </div>
        <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.05)' }}>
          <div
            className="h-full transition-all"
            style={{ width: `${pct}%`, background: 'linear-gradient(90deg, #0d9488, #14b8a6)' }}
          />
        </div>
      </div>

      <SolverLogConsole lines={solveLog} status={solveStatus} onCancel={cancelSolve} />

      {/* Done — go to results */}
      {solveStatus === 'done' && (
        <div className="mt-6 flex justify-end">
          <button
            onClick={() => navigate('/results')}
            className="btn-teal px-5 py-2.5 rounded-lg text-sm font-bold text-white flex items-center gap-2"
          >
            View results <ArrowRight size={14} />
          </button>
        </div>
      )}
    </div>
  )
}

function Pill({ icon: Icon, label, value }) {
  return (
    <div className="glass-panel rounded-xl px-4 py-3 flex items-center gap-3">
      <Icon size={16} className="text-teal-400 flex-shrink-0" />
      <div>
        <p className="text-[9px] uppercase font-bold tracking-widest text-slate-500">{label}</p>
        <p style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '13.5px', fontWeight: 600, color: '#f0f4f8' }}>{value}</p>
      </div>
    </div>
  )
}

function fmtInr(v) {
  if (v == null) return '—'
  return `₹ ${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
}
