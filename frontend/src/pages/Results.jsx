// Step 4 — 7-tab results view. Tabs mirror the output Excel sheets.
// Order_Assignment and Order_Timeline use react-tabulator for sort/filter on 10k rows.

import { useState } from 'react'
import { Download, ChevronRight } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'
import KpiCard from '../components/KpiCard.jsx'
import DataTable from '../components/DataTable.jsx'

const TABS = [
  { id: 'summary',    label: 'Summary' },
  { id: 'assignment', label: 'Order Assignment' },
  { id: 'timeline',   label: 'Order Timeline' },
  { id: 'trips',      label: 'Trip Plan' },
  { id: 'nodes',      label: 'Node Utilization' },
  { id: 'recos',      label: 'Recommendations' },
  { id: 'costcmp',    label: 'Cost Comparison' },
]

export default function Results() {
  const { resultData, downloadOutput } = useApp()
  const [tab, setTab] = useState('summary')

  if (!resultData) {
    return (
      <div className="max-w-4xl mx-auto pt-20 text-center text-slate-400">
        No result available yet. Run a solve first.
      </div>
    )
  }
  const { summary, order_assignment, order_timeline, trip_plan, node_utilization, recommendations, cost_comparison } = resultData

  return (
    <div className="max-w-7xl mx-auto fade-in-up">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-teal-400 mb-2">Step 4 · Results</p>
          <h1 className="text-gradient-teal" style={{ fontFamily: 'Syne, sans-serif', fontSize: '32px', fontWeight: 700, letterSpacing: '-0.02em' }}>
            {summary.method_used} · {summary.status}
          </h1>
          <p className="text-slate-400 mt-1">
            Run {summary.run_id} · wave {summary.active_wave} · wall {summary.wall_time_sec?.toFixed(1)}s
          </p>
        </div>
        <button
          onClick={downloadOutput}
          className="btn-teal px-4 py-2.5 rounded-lg text-sm font-bold text-white flex items-center gap-2"
        >
          <Download size={14} /> Download Output Excel
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2.5 text-xs font-semibold transition-all relative ${
              tab === t.id ? 'text-teal-300' : 'text-slate-500 hover:text-slate-300'
            }`}
            style={tab === t.id ? { borderBottom: '2px solid #0d9488', marginBottom: '-1px' } : undefined}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Panels */}
      {tab === 'summary' && <SummaryPanel summary={summary} />}
      {tab === 'assignment' && (
        <DataTable
          columns={[
            { key: 'order_id', label: 'Order ID' },
            { key: 'route_type', label: 'Route' },
            { key: 'fc', label: 'FC' },
            { key: 'sc', label: 'SC' },
            { key: 'ds', label: 'DS' },
            { key: 'carrier', label: 'Carrier' },
            { key: 'vehicle', label: 'Vehicle' },
            { key: 'load_type', label: 'Load' },
            { key: 'trip_id', label: 'Trip' },
            { key: 'sla_status', label: 'SLA' },
          ]}
          rows={order_assignment || []}
        />
      )}
      {tab === 'timeline' && (
        <DataTable
          columns={[
            { key: 'order_id', label: 'Order' },
            { key: 'fc_dispatch', label: 'FC Dispatch' },
            { key: 'sc_arrival', label: 'SC Arr.' },
            { key: 'sc_dispatch', label: 'SC Disp.' },
            { key: 'ds_arrival', label: 'DS Arr.' },
            { key: 'ds_dispatch', label: 'DS Disp.' },
            { key: 'customer_eta', label: 'Customer ETA' },
            { key: 'ops_sla_deadline', label: 'Ops Deadline' },
            { key: 'sla_status', label: 'SLA' },
          ]}
          rows={order_timeline || []}
        />
      )}
      {tab === 'trips' && (
        <DataTable
          columns={[
            { key: 'trip_id', label: 'Trip' },
            { key: 'lane_type', label: 'Lane Type' },
            { key: 'lane', label: 'Lane' },
            { key: 'carrier', label: 'Carrier' },
            { key: 'vehicle', label: 'Vehicle' },
            { key: 'load_type', label: 'Load' },
            { key: 'parcels', label: 'Parcels' },
            { key: 'distance_km', label: 'Distance km' },
            { key: 'fill_weight_pct', label: 'Fill %' },
          ]}
          rows={trip_plan || []}
        />
      )}
      {tab === 'nodes' && (
        <DataTable
          columns={[
            { key: 'node_id', label: 'Node' },
            { key: 'node_type', label: 'Type' },
            { key: 'load_parcels', label: 'Load' },
            { key: 'capacity_parcels', label: 'Capacity' },
            { key: 'utilization_pct', label: 'Util %' },
            { key: 'bottleneck_flag', label: 'Flag' },
            { key: 'notes', label: 'Notes' },
          ]}
          rows={node_utilization || []}
          maxRows={500}
        />
      )}
      {tab === 'recos' && <RecommendationsPanel recos={recommendations} />}
      {tab === 'costcmp' && <CostComparisonPanel ccmp={cost_comparison} />}
    </div>
  )
}

function SummaryPanel({ summary }) {
  const c = summary.cost
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-4 gap-3">
        <KpiCard label="Total Cost"     value={`₹ ${(c.total_inr || 0).toLocaleString()}`}
                 sub={`gap ${summary.achieved_gap_pct?.toFixed(2) ?? '—'}%`} />
        <KpiCard label="FC Fixed"       value={`₹ ${(c.fc_fixed_cost_inr || 0).toLocaleString()}`} accent="slate" />
        <KpiCard label="Carrier Cost"   value={`₹ ${(c.carrier_cost_inr || 0).toLocaleString()}`} accent="teal" />
        <KpiCard label="SLA Penalty"    value={`₹ ${(c.sla_penalty_inr || 0).toLocaleString()}`} accent="rose" />
      </div>
      <div className="grid grid-cols-4 gap-3">
        <KpiCard label="Orders"           value={summary.total_orders?.toLocaleString() ?? '—'} />
        <KpiCard label="via Courier"      value={summary.orders_via_courier ?? '—'} accent="amber" />
        <KpiCard label="via Hub-Spoke"    value={summary.orders_via_hub_spoke ?? '—'} accent="teal" />
        <KpiCard label="via FC-Direct"    value={summary.orders_via_fc_direct ?? '—'} accent="amber" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <KpiCard label="SLA Met %"        value={`${summary.sla_met_pct ?? '—'}%`} accent="teal" />
        <KpiCard label="Wall Time"        value={`${summary.wall_time_sec?.toFixed(1) ?? '—'} s`} />
      </div>
    </div>
  )
}

function RecommendationsPanel({ recos }) {
  if (!recos) return null
  const cards = [
    ['Under-utilized FCs',                'card1_underutilized_fcs'],
    ['Carriers near concentration cap',   'card2_carriers_near_cap'],
    ['FTL consolidation opportunities',   'card3_ftl_consolidation'],
    ['Courier vs Hub-Spoke trade-off',    'card4_courier_vs_hubspoke'],
    ['SLA breach risk',                   'card5_sla_risk'],
    ['Multi-stop opportunities missed',   'card6_multistop_opps'],
  ]
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {cards.map(([title, key]) => (
        <div key={key} className="glass-panel rounded-2xl p-5">
          <p className="text-[10px] uppercase font-bold tracking-widest text-teal-400 mb-2">{title}</p>
          <div className="space-y-2">
            {(recos[key] || []).slice(0, 5).map((row, i) => (
              <div key={i} className="text-xs text-slate-300 flex items-start gap-2">
                <ChevronRight size={12} className="mt-1 text-teal-400 flex-shrink-0" />
                <pre className="font-mono whitespace-pre-wrap text-[11px] text-slate-300">{JSON.stringify(row, null, 0)}</pre>
              </div>
            ))}
            {(!recos[key] || recos[key].length === 0) && (
              <p className="text-xs text-slate-500">No rows in this card.</p>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

function CostComparisonPanel({ ccmp }) {
  if (!ccmp) return null
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-4 gap-3">
        <KpiCard label="Courier-only Baseline" value={`₹ ${ccmp.baseline_cost_inr?.toLocaleString()}`} accent="amber" />
        <KpiCard label="Optimizer"             value={`₹ ${ccmp.optimizer_cost_inr?.toLocaleString()}`} accent="teal" />
        <KpiCard label="Savings (INR)"         value={`₹ ${ccmp.savings_inr?.toLocaleString()}`} accent="teal" />
        <KpiCard label="Savings (%)"           value={`${ccmp.savings_pct?.toFixed(1)}%`} accent="teal" />
      </div>
      <DataTable
        columns={[
          { key: 'route_type', label: 'Route Type' },
          { key: 'orders', label: 'Orders' },
          { key: 'cost_inr', label: 'Cost (INR)' },
          { key: 'avg_inr_per_order', label: 'Avg / order' },
        ]}
        rows={ccmp.breakdown_by_route_type || []}
      />
      <div className="glass-panel rounded-xl p-5">
        <p className="text-[10px] uppercase font-bold tracking-widest text-slate-400 mb-3">Takeaways</p>
        <ul className="space-y-2">
          {(ccmp.takeaways || []).map((t, i) => (
            <li key={i} className="text-xs text-slate-300 flex items-start gap-2">
              <ChevronRight size={12} className="mt-1 text-teal-400 flex-shrink-0" />
              {t}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
