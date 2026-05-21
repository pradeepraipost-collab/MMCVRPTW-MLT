// Step 2 — the 10-method picker (spec §7.5, central UI piece).
// Layout: eyebrow + headline + subtitle, 3-col method grid, reference table,
// MethodExplanationPanel, sticky bottom action bar.

import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Sliders, BarChart3 } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'
import { METHODS } from '../data/methods.js'
import MethodCard from '../components/MethodCard.jsx'
import MethodExplanationPanel from '../components/MethodExplanationPanel.jsx'

export default function Configure() {
  const { selectedMethodId, setSelectedMethodId, startSolve, runBenchmark, benchmarkData } = useApp()
  const navigate = useNavigate()

  const selected = useMemo(
    () => METHODS.find((m) => m.id === selectedMethodId) || null,
    [selectedMethodId]
  )

  return (
    <div className="max-w-7xl mx-auto pb-32 fade-in-up">
      {/* A. Eyebrow + headline */}
      <p className="text-[10px] font-bold uppercase tracking-widest text-teal-400 mb-2">
        Step 2 · Pick solve method
      </p>
      <h1 className="text-gradient-teal" style={{ fontFamily: 'Syne, sans-serif', fontSize: '32px', fontWeight: 700, letterSpacing: '-0.02em' }}>
        Solve time vs proximity to optimum
      </h1>
      <p className="text-slate-400 mt-2 mb-8 max-w-3xl">
        Every method below solves the same MMCVRPTW-MLT problem against the same data. They differ
        in how they search and what they guarantee about the result. Five are implemented today;
        five more are on the Phase 2 roadmap with full transparency about what they would do.
      </p>

      {/* B. Method grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-12">
        {METHODS.map((m) => (
          <MethodCard
            key={m.id}
            method={m}
            selected={selectedMethodId === m.id}
            onSelect={setSelectedMethodId}
          />
        ))}
      </div>

      {/* C. Reference table */}
      <div className="glass-panel rounded-2xl overflow-hidden mb-10">
        <div className="px-5 py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
          <p className="text-[10px] uppercase font-bold tracking-widest text-slate-400">
            Comparison · all 10 methods
          </p>
        </div>
        <table className="w-full" style={{ fontSize: '10.5px' }}>
          <thead>
            <tr style={{ background: 'rgba(13,148,136,0.04)', borderBottom: '1px solid var(--border-subtle)' }}>
              <th className="text-left px-4 py-3 font-bold uppercase tracking-widest text-slate-500">Method</th>
              <th className="text-left px-4 py-3 font-bold uppercase tracking-widest text-slate-500">Solve time</th>
              <th className="text-left px-4 py-3 font-bold uppercase tracking-widest text-slate-500">Confirmed gap</th>
              <th className="text-left px-4 py-3 font-bold uppercase tracking-widest text-slate-500">What you give up</th>
            </tr>
          </thead>
          <tbody>
            {METHODS.map((m) => (
              <tr key={m.id}
                style={{
                  opacity: m.enabled ? 1 : 0.65,
                  borderBottom: '1px solid rgba(255,255,255,0.04)',
                  background: selectedMethodId === m.id ? 'rgba(13,148,136,0.04)' : undefined,
                }}>
                <td className="px-4 py-2.5 text-slate-200">
                  <span className="font-bold mr-2">{m.name}</span>
                  <span className="text-[9px] uppercase tracking-widest text-slate-500">{m.badge}</span>
                </td>
                <td className="px-4 py-2.5 text-slate-300">{m.solveTime}</td>
                <td className="px-4 py-2.5 text-slate-300">{m.gap}</td>
                <td className="px-4 py-2.5 text-slate-400">{m.detail.doesNotSolve[0]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* D. MethodExplanationPanel */}
      {selected && <MethodExplanationPanel method={selected} />}

      {/* Benchmark trigger */}
      <div className="mt-8 rounded-xl p-4 flex items-center justify-between"
        style={{ background: 'rgba(13,148,136,0.04)', border: '1px solid rgba(13,148,136,0.15)' }}>
        <div className="flex items-center gap-3">
          <BarChart3 size={18} className="text-teal-400" />
          <div>
            <p className="text-sm font-semibold text-slate-200">Run benchmark on 1k subset</p>
            <p className="text-xs text-slate-500">All 5 methods, sequentially. ~15 min.</p>
          </div>
        </div>
        <button
          onClick={runBenchmark}
          className="px-4 py-2 rounded-md text-xs font-bold uppercase tracking-wider transition-all"
          style={{
            background: 'rgba(13,148,136,0.1)',
            border: '1px solid rgba(13,148,136,0.3)',
            color: '#2dd4bf',
          }}
        >
          {benchmarkData?.running ? 'Running…' : 'Start benchmark'}
        </button>
      </div>
      {benchmarkData?.results && (
        <div className="glass-panel rounded-xl overflow-hidden mt-4">
          <div className="px-4 py-2 text-[10px] uppercase font-bold tracking-widest text-slate-400"
            style={{ borderBottom: '1px solid var(--border-subtle)' }}>
            Benchmark — 1k subset · seed {benchmarkData.seed}
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr style={{ background: 'rgba(13,148,136,0.04)' }}>
                <th className="text-left px-3 py-2 text-[10px] uppercase tracking-widest text-slate-500">Method</th>
                <th className="text-left px-3 py-2 text-[10px] uppercase tracking-widest text-slate-500">Cost (INR)</th>
                <th className="text-left px-3 py-2 text-[10px] uppercase tracking-widest text-slate-500">Wall (s)</th>
                <th className="text-left px-3 py-2 text-[10px] uppercase tracking-widest text-slate-500">Gap %</th>
                <th className="text-left px-3 py-2 text-[10px] uppercase tracking-widest text-slate-500">Status</th>
              </tr>
            </thead>
            <tbody>
              {benchmarkData.results.map((r, i) => (
                <tr key={i} style={{ borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                  <td className="px-3 py-1.5 text-slate-200 font-semibold">{r.method}</td>
                  <td className="px-3 py-1.5 text-slate-300">{r.cost_inr?.toLocaleString() ?? '—'}</td>
                  <td className="px-3 py-1.5 text-slate-300">{r.wall_time_sec}</td>
                  <td className="px-3 py-1.5 text-slate-300">{r.gap_pct ?? '—'}</td>
                  <td className="px-3 py-1.5 text-slate-400 font-mono text-[10.5px]">{r.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* E. Sticky bottom action bar */}
      <div
        className="fixed bottom-0 left-60 right-0 px-8 py-4 flex items-center justify-between"
        style={{
          background: 'rgba(6,12,18,0.92)',
          backdropFilter: 'blur(12px)',
          borderTop: '1px solid var(--border-subtle)',
          zIndex: 40,
        }}
      >
        <div>
          {selected ? (
            <>
              <p className="text-[10px] uppercase font-bold tracking-widest text-slate-500">Selected</p>
              <p className="text-sm text-slate-200">
                <span className="font-bold">{selected.name}</span>
                <span className="text-slate-500"> · expect {selected.solveTime}</span>
              </p>
            </>
          ) : (
            <p className="text-sm text-slate-500">Pick a method above to enable Run.</p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button
            disabled
            className="px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider flex items-center gap-1.5 cursor-not-allowed"
            style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', color: '#475569' }}
          >
            <Sliders size={12} /> Advanced options
          </button>
          <button
            disabled={!selected}
            onClick={() => { startSolve(); navigate('/solve') }}
            className={`px-5 py-2.5 rounded-lg text-sm font-bold flex items-center gap-2 transition-all ${
              selected ? 'btn-teal text-white' : 'cursor-not-allowed text-slate-700'
            }`}
            style={!selected ? { background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' } : undefined}
          >
            Run solver <ArrowRight size={14} />
          </button>
        </div>
      </div>
    </div>
  )
}
