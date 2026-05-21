// Data Explorer — pre-solve sanity check on what was loaded. Lists sheet counts.
// Detailed row-level browsing is intentionally minimal here; users open the
// .xlsx directly for deep inspection.

import { useApp } from '../context/AppContext.jsx'
import KpiCard from '../components/KpiCard.jsx'

export default function DataExplorer() {
  const { uploadMeta, masterSummary } = useApp()
  if (!masterSummary) {
    return <div className="max-w-4xl mx-auto pt-20 text-center text-slate-400">Upload master first.</div>
  }
  const lanes = uploadMeta?.preview_stats?.lanes_by_type || {}
  return (
    <div className="max-w-6xl mx-auto fade-in-up">
      <p className="text-[10px] font-bold uppercase tracking-widest text-teal-400 mb-2">Data Explorer</p>
      <h1 className="text-gradient-teal" style={{ fontFamily: 'Syne, sans-serif', fontSize: '32px', fontWeight: 700, letterSpacing: '-0.02em' }}>
        Loaded master data
      </h1>
      <p className="text-slate-400 mt-2 mb-8">
        Sheet-level summary of <span className="font-mono text-teal-300">{uploadMeta?.filename}</span>.
        For row-level detail, open the .xlsx directly.
      </p>
      <div className="grid grid-cols-4 gap-3 mb-6">
        <KpiCard label="Origin_Master"          value={masterSummary.fcs} sub="FCs" />
        <KpiCard label="Intermediate_Master"    value={masterSummary.scs} sub="SCs" />
        <KpiCard label="Destination_Master"     value={masterSummary.dses_active + masterSummary.dses_minor}
                 sub={`${masterSummary.dses_active} active · ${masterSummary.dses_minor} minor`} />
        <KpiCard label="Carrier_Master"         value={masterSummary.carriers} sub="unique carriers" />
      </div>
      <div className="grid grid-cols-4 gap-3 mb-6">
        <KpiCard label="Vehicle_Types"          value={masterSummary.vehicles} />
        <KpiCard label="Lane_Distance_Matrix"   value={(masterSummary.lanes_fc_sc + masterSummary.lanes_sc_ds + masterSummary.lanes_fc_ds_direct + masterSummary.lanes_sc_sc).toLocaleString()}
                 sub="total lanes" accent="amber" />
        <KpiCard label="Order_Data"             value={masterSummary.orders.toLocaleString()} sub="this wave" />
        <KpiCard label="Active Wave"            value={masterSummary.active_order_wave} sub={masterSummary.active_dispatch_wave} />
      </div>
      <div className="glass-panel rounded-2xl p-5">
        <p className="text-[10px] uppercase font-bold tracking-widest text-slate-400 mb-3">Lane distribution</p>
        <div className="grid grid-cols-4 gap-3">
          <div><p className="text-[10px] text-slate-500 uppercase">FC→SC</p><p className="text-xl text-slate-200 font-mono">{masterSummary.lanes_fc_sc}</p></div>
          <div><p className="text-[10px] text-slate-500 uppercase">SC→DS</p><p className="text-xl text-slate-200 font-mono">{masterSummary.lanes_sc_ds}</p></div>
          <div><p className="text-[10px] text-slate-500 uppercase">FC→DS direct</p><p className="text-xl text-slate-200 font-mono">{masterSummary.lanes_fc_ds_direct}</p></div>
          <div><p className="text-[10px] text-slate-500 uppercase">SC↔SC</p><p className="text-xl text-slate-200 font-mono">{masterSummary.lanes_sc_sc}</p></div>
        </div>
      </div>
    </div>
  )
}
