// Step 1 — drag-drop the 15-sheet master xlsx.
// Shows the strict §6 validation result; on success, shows preview cards from
// preview_stats and links forward to Configure.

import { useCallback, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Upload as UploadIcon, FileSpreadsheet, CheckCircle2, AlertTriangle, ArrowRight } from 'lucide-react'
import { useApp } from '../context/AppContext.jsx'
import KpiCard from '../components/KpiCard.jsx'

export default function Upload() {
  const { uploadStatus, uploadMeta, uploadError, uploadFile, masterSummary } = useApp()
  const navigate = useNavigate()
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef(null)

  const onFile = useCallback((file) => {
    if (file && (file.name.endsWith('.xlsx') || file.type.includes('spreadsheet'))) {
      uploadFile(file)
    }
  }, [uploadFile])

  return (
    <div className="max-w-5xl mx-auto fade-in-up">
      <p className="text-[10px] font-bold uppercase tracking-widest text-teal-400 mb-2">Step 1 · Upload Master</p>
      <h1 className="text-gradient-teal" style={{ fontFamily: 'Syne, sans-serif', fontSize: '32px', fontWeight: 700, letterSpacing: '-0.02em' }}>
        The 15-sheet master workbook
      </h1>
      <p className="text-slate-400 mt-2 mb-8">
        Drop your <span className="font-mono text-teal-300">MMCVRPTW_MLT_MasterData_V4.xlsx</span>.
        Sheet 15 (<span className="font-mono">Order_Data</span>) must have all 20 columns populated —
        the upload is rejected otherwise (spec §6).
      </p>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); onFile(e.dataTransfer.files[0]) }}
        onClick={() => fileRef.current?.click()}
        className="glass-panel rounded-2xl p-12 text-center cursor-pointer transition-all"
        style={{
          border: dragOver ? '2px dashed rgba(13,148,136,0.5)' : '2px dashed rgba(255,255,255,0.08)',
          background: dragOver ? 'rgba(13,148,136,0.04)' : undefined,
        }}
      >
        <UploadIcon size={36} className="mx-auto text-teal-400 mb-3" />
        <p style={{ fontFamily: 'Syne, sans-serif', fontSize: '18px', fontWeight: 600, color: '#f0f4f8' }}>
          {uploadStatus === 'uploading' ? 'Uploading & validating…' :
           uploadStatus === 'success'   ? `Loaded: ${uploadMeta?.filename}` :
           'Drop the .xlsx here, or click to browse'}
        </p>
        <p className="text-xs text-slate-500 mt-2">15 sheets · 10k+ orders · row 1 banner / row 2 headers</p>
        <input ref={fileRef} type="file" accept=".xlsx" className="hidden"
          onChange={(e) => onFile(e.target.files?.[0])} />
      </div>

      {/* Errors */}
      {uploadStatus === 'error' && (
        <div className="mt-6 rounded-xl p-4 flex gap-3"
          style={{ background: 'rgba(244,63,94,0.06)', border: '1px solid rgba(244,63,94,0.3)' }}>
          <AlertTriangle size={18} className="text-rose-400 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-[10px] uppercase font-bold tracking-widest text-rose-400 mb-1">Upload rejected</p>
            <pre className="text-xs text-slate-300 whitespace-pre-wrap font-mono">{uploadError}</pre>
            <p className="text-[11px] text-slate-500 mt-2">
              V4 spec §6 forbids silent recovery — fix the master file and try again.
            </p>
          </div>
        </div>
      )}

      {/* Success preview */}
      {uploadStatus === 'success' && masterSummary && (
        <>
          <div className="mt-8 flex items-center gap-2">
            <CheckCircle2 size={16} className="text-emerald-400" />
            <p className="text-sm text-slate-300">Master loaded and validated. All 15 sheets present, Order_Data has 20 columns populated.</p>
          </div>
          <div className="grid grid-cols-4 gap-3 mt-6">
            <KpiCard label="FCs"               value={masterSummary.fcs} />
            <KpiCard label="SCs"               value={masterSummary.scs} />
            <KpiCard label="Active DSes"       value={masterSummary.dses_active} sub={`+ ${masterSummary.dses_minor} minor`} />
            <KpiCard label="Carriers"          value={masterSummary.carriers} />
            <KpiCard label="Vehicles"          value={masterSummary.vehicles} />
            <KpiCard label="Lanes (FC→SC)"     value={masterSummary.lanes_fc_sc} accent="amber" />
            <KpiCard label="Lanes (SC→DS)"     value={masterSummary.lanes_sc_ds} accent="amber" />
            <KpiCard label="Lanes (FC→DS dir)" value={masterSummary.lanes_fc_ds_direct} accent="amber" />
          </div>
          <div className="grid grid-cols-2 gap-3 mt-3">
            <KpiCard label="Orders" value={masterSummary.orders.toLocaleString()} sub={`Wave: ${masterSummary.active_order_wave}`} />
            <KpiCard label="Dispatch wave" value={masterSummary.active_dispatch_wave} sub="Active dispatch window" />
          </div>
          <div className="mt-8 flex justify-end">
            <button
              onClick={() => navigate('/configure')}
              className="btn-teal px-5 py-2.5 rounded-lg text-sm font-bold text-white flex items-center gap-2"
            >
              Next: pick a solve method <ArrowRight size={14} />
            </button>
          </div>
        </>
      )}
    </div>
  )
}
