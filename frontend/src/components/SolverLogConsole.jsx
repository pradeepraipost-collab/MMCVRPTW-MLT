// SolverLogConsole — JetBrains Mono line-numbered log viewer for the Solve page.
// Auto-scrolls to bottom as new lines arrive. Cancel button (red) top-right.

import { useEffect, useRef } from 'react'
import { Square, Activity } from 'lucide-react'

export default function SolverLogConsole({ lines, status, onCancel }) {
  const ref = useRef(null)
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight
  }, [lines])
  const isRunning = status === 'running'
  return (
    <div className="glass-panel rounded-2xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <div className="flex items-center gap-2">
          <Activity size={14} className={isRunning ? 'text-emerald-400 animate-pulse' : 'text-slate-500'} />
          <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
            Solver log · {status}
          </span>
        </div>
        {isRunning && (
          <button
            onClick={onCancel}
            className="px-3 py-1.5 rounded-md text-[11px] font-bold uppercase tracking-wider flex items-center gap-1.5 transition-all"
            style={{
              background: 'rgba(244,63,94,0.1)',
              border: '1px solid rgba(244,63,94,0.3)',
              color: '#fb7185',
            }}
          >
            <Square size={11} fill="currentColor" />
            Cancel
          </button>
        )}
      </div>
      <div
        ref={ref}
        className="overflow-y-auto scrollbar-thin"
        style={{
          height: '420px',
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: '11.5px',
          background: '#060c12',
        }}
      >
        {lines.length === 0 && (
          <div className="px-4 py-4 text-slate-600">Waiting for solver output…</div>
        )}
        {lines.map((line, i) => (
          <div key={i} className="px-4 py-0.5 flex gap-3 hover:bg-white/[0.02]">
            <span className="text-slate-700 select-none" style={{ width: '40px', textAlign: 'right' }}>
              {String(i + 1).padStart(4, ' ')}
            </span>
            <span className="text-slate-300 whitespace-pre-wrap break-all">{line}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
