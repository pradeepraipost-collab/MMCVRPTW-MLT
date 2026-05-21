// Home — Network Overview. Master data summary + light explanation.

import { Link } from 'react-router-dom'
import { ArrowRight, Network, Truck, Building2, MapPin } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'
import KpiCard from '../components/KpiCard.jsx'

export default function InputDashboard() {
  const { uploadStatus, masterSummary } = useApp()
  return (
    <div className="max-w-6xl mx-auto fade-in-up">
      <p className="text-[10px] font-bold uppercase tracking-widest text-amber-400 mb-2">
        Network Overview · Pre-solve
      </p>
      <h1 className="text-gradient-teal" style={{ fontFamily: 'Syne, sans-serif', fontSize: '32px', fontWeight: 700, letterSpacing: '-0.02em' }}>
        MMCVRPTW-MLT Wave Optimiser
      </h1>
      <p className="text-slate-400 mt-2 mb-8 max-w-3xl">
        Three-tier ecommerce fulfilment network with FCs → SCs → DSes, multi-load-type carriers
        (FTL / PTL / LTL / Courier), and time-windowed SLA penalties. Solve method chosen on
        the Configure page; five methods implemented, five more on the Phase 2 roadmap.
      </p>

      {uploadStatus !== 'success' ? (
        <div className="glass-panel rounded-2xl p-8 text-center">
          <Network size={32} className="mx-auto text-teal-400 mb-3" />
          <h3 style={{ fontFamily: 'Syne, sans-serif', fontSize: '18px', fontWeight: 600 }}>
            No master loaded yet
          </h3>
          <p className="text-slate-400 mt-1 mb-4">Drop the 15-sheet workbook to begin.</p>
          <Link to="/upload" className="btn-teal px-4 py-2.5 rounded-lg text-sm font-bold text-white inline-flex items-center gap-2">
            Go to Upload <ArrowRight size={14} />
          </Link>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-4 gap-3 mb-6">
            <KpiCard label="FCs"            value={masterSummary?.fcs} />
            <KpiCard label="SCs"            value={masterSummary?.scs} />
            <KpiCard label="Active DSes"    value={masterSummary?.dses_active} sub={`+ ${masterSummary?.dses_minor} minor`} />
            <KpiCard label="Carriers"       value={masterSummary?.carriers} />
          </div>
          <div className="grid grid-cols-3 gap-3 mb-6">
            <KpiCard label="Orders"             value={(masterSummary?.orders || 0).toLocaleString()} accent="teal" />
            <KpiCard label="FC→SC lanes"        value={masterSummary?.lanes_fc_sc} accent="amber" />
            <KpiCard label="SC→DS lanes"        value={masterSummary?.lanes_sc_ds} accent="amber" />
          </div>
          <div className="glass-panel rounded-2xl p-5">
            <p className="text-[10px] uppercase font-bold tracking-widest text-slate-400 mb-2">Active Waves</p>
            <p className="text-sm text-slate-200 font-mono">
              <Building2 size={12} className="inline mr-1.5 text-teal-400" />
              {masterSummary?.active_order_wave} (placement)
            </p>
            <p className="text-sm text-slate-200 font-mono mt-1">
              <Truck size={12} className="inline mr-1.5 text-teal-400" />
              {masterSummary?.active_dispatch_wave} (dispatch)
            </p>
          </div>
          <div className="mt-8 flex justify-end">
            <Link to="/configure"
              className="btn-teal px-5 py-2.5 rounded-lg text-sm font-bold text-white inline-flex items-center gap-2">
              Pick a method <ArrowRight size={14} />
            </Link>
          </div>
        </>
      )}
    </div>
  )
}
