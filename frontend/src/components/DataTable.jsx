// Lightweight scrolling table used on Data Explorer / Node Utilization tabs.
// For 10k-row tables (Order_Assignment, Order_Timeline) we use react-tabulator
// directly in Results.jsx; this component is the simpler fallback.

export default function DataTable({ columns, rows, maxRows = 200 }) {
  const visible = rows.slice(0, maxRows)
  const truncated = rows.length - visible.length
  return (
    <div className="glass-panel rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm" style={{ fontSize: '12px' }}>
          <thead>
            <tr style={{ background: 'rgba(13,148,136,0.06)', borderBottom: '1px solid rgba(13,148,136,0.15)' }}>
              {columns.map((c) => (
                <th key={c.key || c} className="text-left px-3 py-2.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  {c.label || c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row, i) => (
              <tr key={i} className="hover:bg-white/[0.02]" style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                {columns.map((c) => (
                  <td key={c.key || c} className="px-3 py-2 text-slate-300">
                    {String(row[c.key || c] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {truncated > 0 && (
        <div className="text-center py-2 text-[10px] text-slate-500" style={{ borderTop: '1px solid rgba(255,255,255,0.04)' }}>
          … {truncated.toLocaleString()} more rows
        </div>
      )}
    </div>
  )
}
