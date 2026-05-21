// Adapted from ui_reference/src/components/Sidebar.jsx per spec §7.3.
// Three groups: Setup / Input / Output. MMCVRPTW logo replaces WaveLoad. No
// profile badge (V4 has a single profile). Disabled states use the reference's
// exact styling.

import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Upload, Table2, Settings2, Play, Map, ListChecks,
  BarChart3, ArrowRight, RotateCcw, Truck,
} from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'

export default function Sidebar() {
  const {
    uploadStatus, solveStatus, selectedMethodId, resetAll,
  } = useApp()
  const navigate = useNavigate()
  const hasData = uploadStatus === 'success'
  const isRunning = solveStatus === 'running'
  const isDone = solveStatus === 'done'

  return (
    <aside
      className="fixed top-0 left-0 h-screen w-60 flex flex-col z-50"
      style={{
        background: 'linear-gradient(180deg, #0a1219 0%, #060c12 100%)',
        borderRight: '1px solid rgba(13,148,136,0.12)',
      }}
    >
      {/* Logo */}
      <div className="px-5 py-5" style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center"
            style={{
              background: 'linear-gradient(135deg, #0d9488, #0f766e)',
              boxShadow: '0 4px 16px rgba(13,148,136,0.4), 0 0 0 1px rgba(13,148,136,0.2)',
            }}
          >
            <Truck size={16} className="text-white" />
          </div>
          <div>
            <p style={{ fontFamily: 'Syne, sans-serif', fontSize: '14px', fontWeight: 700, color: '#f0f4f8', letterSpacing: '-0.02em' }}>
              MMCVRPTW
            </p>
            <p style={{ fontSize: '9px', color: '#0d9488', fontWeight: 700, letterSpacing: '0.15em', textTransform: 'uppercase' }}>
              MULTI LOAD TYPE
            </p>
          </div>
        </div>
      </div>

      {/* Reset */}
      <div className="px-3 pt-3 pb-1">
        <button
          onClick={resetAll}
          disabled={isRunning}
          className={`w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg border text-xs font-semibold transition-all ${
            isRunning
              ? 'border-slate-800 text-slate-700 cursor-not-allowed'
              : 'border-red-900/30 text-red-500/50 hover:border-red-600/50 hover:text-red-400 hover:bg-red-950/20'
          }`}
        >
          <RotateCcw size={11} />
          Reset All
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-2 space-y-3 scrollbar-thin">
        {/* SETUP */}
        <div>
          <p className="text-[9px] font-bold uppercase tracking-widest mb-2 px-1" style={{ color: '#334155', letterSpacing: '0.12em' }}>Setup</p>
          <ToolLink to="/upload" icon={Upload} label="Upload Master" />
          <ToolLink to="/configure" icon={Settings2} label="Configure" disabled={!hasData} disabledTip="Upload master first" />
          <ToolLink to="/solve" icon={Play} label="Run" disabled={!hasData || !selectedMethodId} disabledTip="Pick a method first" />
          <ToolLink to="/data" icon={Table2} label="Data Explorer" disabled={!hasData} disabledTip="Upload master first" />
        </div>

        {/* INPUT */}
        <div className="rounded-xl overflow-hidden" style={{ background: 'rgba(255,180,0,0.03)', border: '1px solid rgba(255,180,0,0.08)' }}>
          <div className="px-3 py-2" style={{ borderBottom: '1px solid rgba(255,180,0,0.08)' }}>
            <p className="text-[9px] font-bold uppercase tracking-widest flex items-center gap-1.5" style={{ color: 'rgba(251,191,36,0.6)', letterSpacing: '0.12em' }}>
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
              Input
            </p>
          </div>
          <SidebarLink to="/" end icon={LayoutDashboard} label="Network Overview" badge="PRE" badgeColor="amber" />
        </div>

        {/* OUTPUT */}
        <div className="rounded-xl overflow-hidden" style={{ background: 'rgba(13,148,136,0.03)', border: '1px solid rgba(13,148,136,0.08)' }}>
          <div className="px-3 py-2" style={{ borderBottom: '1px solid rgba(13,148,136,0.08)' }}>
            <p className="text-[9px] font-bold uppercase tracking-widest flex items-center gap-1.5" style={{ color: 'rgba(13,148,136,0.6)', letterSpacing: '0.12em' }}>
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: '#0d9488' }} />
              Output
            </p>
          </div>
          <SidebarLink to="/results"        icon={BarChart3}  label="Wave KPIs"       badge="POST" badgeColor="teal" disabled={!isDone} disabledTip="Run optimizer first" />
          <SidebarLink to="/results#maps"   icon={Map}        label="Route Maps"      badge="MAP"  badgeColor="teal" disabled={!isDone} disabledTip="Run optimizer first" />
          <SidebarLink to="/results#recos"  icon={ListChecks} label="Recommendations" badge="REC"  badgeColor="teal" disabled={!isDone} disabledTip="Run optimizer first" />
        </div>
      </nav>

      {/* Status footer */}
      <div className="px-4 py-4" style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}>
        <div className="space-y-2">
          <StatusDot label="Master Data" ok={hasData} />
          <StatusDot label="Optimizer"   ok={isDone}  warn={isRunning} warnLabel="Running…" />
        </div>
        {isDone && (
          <button
            onClick={() => navigate('/results')}
            className="w-full flex items-center justify-center gap-1.5 mt-3 px-3 py-2 rounded-lg text-xs font-semibold transition-all"
            style={{
              background: 'rgba(13,148,136,0.1)',
              border: '1px solid rgba(13,148,136,0.25)',
              color: '#2dd4bf',
            }}
          >
            View Solution <ArrowRight size={11} />
          </button>
        )}
      </div>
    </aside>
  )
}

function ToolLink({ to, icon: Icon, label, disabled, disabledTip, title }) {
  if (disabled) {
    return (
      <div title={disabledTip} className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium cursor-not-allowed mb-0.5" style={{ color: '#1e3040' }}>
        <Icon size={14} style={{ opacity: 0.2 }} />
        {label}
      </div>
    )
  }
  return (
    <NavLink
      to={to}
      title={title}
      className={({ isActive }) =>
        `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 mb-0.5 ${
          isActive ? 'text-white' : 'text-slate-500 hover:text-slate-200'
        }`
      }
      style={({ isActive }) => isActive ? {
        background: 'linear-gradient(135deg, rgba(13,148,136,0.2), rgba(13,148,136,0.08))',
        border: '1px solid rgba(13,148,136,0.3)',
        boxShadow: '0 0 12px rgba(13,148,136,0.1)',
      } : { background: 'transparent', border: '1px solid transparent' }}
    >
      {({ isActive }) => (
        <>
          <Icon size={14} style={{ color: isActive ? '#2dd4bf' : undefined }} />
          {label}
        </>
      )}
    </NavLink>
  )
}

function SidebarLink({ to, end, icon: Icon, label, badge, badgeColor, disabled, disabledTip }) {
  const bp = {
    amber: { bg: 'rgba(251,191,36,0.1)', color: '#fbbf24', border: 'rgba(251,191,36,0.2)' },
    teal:  { bg: 'rgba(13,148,136,0.1)', color: '#2dd4bf', border: 'rgba(13,148,136,0.2)' },
  }[badgeColor] || { bg: 'rgba(13,148,136,0.1)', color: '#2dd4bf', border: 'rgba(13,148,136,0.2)' }

  if (disabled) {
    return (
      <div title={disabledTip} className="flex items-center gap-2 px-3 py-2.5 text-xs font-medium cursor-not-allowed" style={{ color: '#1e3040' }}>
        <Icon size={13} style={{ opacity: 0.2 }} />
        <span className="flex-1">{label}</span>
        {badge && <span className="text-[9px] px-1.5 py-0.5 rounded font-bold" style={{ background: 'rgba(255,255,255,0.03)', color: '#1e3040' }}>{badge}</span>}
      </div>
    )
  }
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `flex items-center gap-2 px-3 py-2.5 text-xs font-semibold transition-all ${
          isActive ? 'text-white' : 'text-slate-500 hover:text-slate-300'
        }`
      }
      style={({ isActive }) => isActive ? {
        background: 'rgba(13,148,136,0.08)',
        borderLeft: '2px solid #0d9488', paddingLeft: '10px',
      } : { borderLeft: '2px solid transparent' }}
    >
      {({ isActive }) => (
        <>
          <Icon size={13} style={{ color: isActive ? '#0d9488' : undefined, opacity: isActive ? 1 : 0.4 }} />
          <span className="flex-1">{label}</span>
          {badge && (
            <span className="text-[9px] px-1.5 py-0.5 rounded font-bold"
              style={{ background: bp.bg, color: bp.color, border: `1px solid ${bp.border}` }}>
              {badge}
            </span>
          )}
        </>
      )}
    </NavLink>
  )
}

function StatusDot({ label, ok, warn, warnLabel }) {
  return (
    <div className="flex items-center gap-2">
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${ok ? '' : warn ? 'animate-pulse' : ''}`}
        style={{ background: ok ? '#10b981' : warn ? '#f59e0b' : '#1e3040' }} />
      <span className="text-xs" style={{ color: '#334155' }}>{label}</span>
      {warn && <span className="text-xs text-amber-400 ml-auto">{warnLabel}</span>}
      {ok && <span className="text-xs text-emerald-500 ml-auto">Ready</span>}
    </div>
  )
}
