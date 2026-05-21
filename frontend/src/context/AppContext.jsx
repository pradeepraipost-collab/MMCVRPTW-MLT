import { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

const Ctx = createContext(null)
const API = '/api'

// V4: single solver profile. No multi-profile state. Method picker lives in
// Configure.jsx and resolves to a method_id string passed to /api/solve.

export function AppProvider({ children }) {
  // Upload state
  const [uploadStatus, setUploadStatus] = useState('idle')    // idle | uploading | success | error
  const [uploadMeta, setUploadMeta]     = useState(null)      // { filename, preview_stats }
  const [uploadError, setUploadError]   = useState(null)
  const [runId, setRunId]               = useState(null)
  const [masterSummary, setMasterSummary] = useState(null)

  // Method selection (Configure page)
  const [selectedMethodId, setSelectedMethodId] = useState(null)

  // Solve state
  const [solveStatus, setSolveStatus]   = useState('idle')    // idle | running | done | error | cancelled
  const [solveLog, setSolveLog]         = useState([])
  const [solveStats, setSolveStats]     = useState({ elapsed_sec: 0, incumbent: null, bound: null, gap_pct: null })

  // Result state
  const [resultData, setResultData]     = useState(null)
  const [benchmarkData, setBenchmarkData] = useState(null)

  const sseRef = useRef(null)

  const resetAll = useCallback(async () => {
    if (sseRef.current) { sseRef.current.close(); sseRef.current = null }
    setUploadStatus('idle'); setUploadMeta(null); setUploadError(null); setRunId(null)
    setMasterSummary(null); setSelectedMethodId(null)
    setSolveStatus('idle'); setSolveLog([]); setSolveStats({ elapsed_sec: 0, incumbent: null, bound: null, gap_pct: null })
    setResultData(null); setBenchmarkData(null)
  }, [])

  const uploadFile = useCallback(async (file) => {
    setUploadStatus('uploading'); setUploadError(null); setUploadMeta(null)
    setResultData(null); setSolveStatus('idle'); setSolveLog([])
    const fd = new FormData(); fd.append('file', file)
    try {
      const res = await fetch(`${API}/upload`, { method: 'POST', body: fd })
      const data = await res.json()
      if (res.ok && data.validation?.ok) {
        setUploadStatus('success')
        setRunId(data.run_id)
        setUploadMeta({ filename: data.filename, preview_stats: data.preview_stats })
        // Fetch master summary
        const sumRes = await fetch(`${API}/master_summary/${data.run_id}`)
        if (sumRes.ok) setMasterSummary(await sumRes.json())
      } else {
        setUploadStatus('error')
        const errMsg = (data.validation?.errors || [])
          .map(e => `${e.sheet ? '[' + e.sheet + (e.column ? ':' + e.column : '') + '] ' : ''}${e.message}`)
          .join('\n') || 'Upload failed'
        setUploadError(errMsg)
      }
    } catch (e) {
      setUploadStatus('error'); setUploadError(e.message)
    }
  }, [])

  const startSolve = useCallback(async () => {
    if (!runId || !selectedMethodId) return
    setSolveStatus('running'); setSolveLog([]); setSolveStats({ elapsed_sec: 0, incumbent: null, bound: null, gap_pct: null })
    setResultData(null)
    try {
      const res = await fetch(`${API}/solve`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: runId, method_id: selectedMethodId }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        setSolveStatus('error')
        setSolveLog(prev => [...prev, `ERROR: ${err.detail || res.statusText}`])
        return
      }
    } catch (e) {
      setSolveStatus('error'); setSolveLog(prev => [...prev, `ERROR: ${e.message}`])
      return
    }

    // Subscribe to SSE
    const es = new EventSource(`${API}/solve_stream/${runId}`)
    sseRef.current = es
    es.addEventListener('log', (e) => setSolveLog(prev => [...prev, e.data]))
    es.addEventListener('status', (e) => {
      try {
        // Backend uses str(dict) so we eval-parse safely as JSON-ish by replacing single quotes
        const parsed = JSON.parse(e.data.replace(/'/g, '"').replace(/None/g, 'null'))
        if (parsed.status) setSolveStatus(parsed.status)
        setSolveStats({
          elapsed_sec: parsed.elapsed_sec || 0,
          incumbent: parsed.incumbent,
          bound: parsed.bound,
          gap_pct: parsed.gap_pct,
        })
      } catch {}
    })
    es.addEventListener('end', async (e) => {
      es.close(); sseRef.current = null
      setSolveStatus(e.data)
      if (e.data === 'done') {
        const r = await fetch(`${API}/result/${runId}`)
        if (r.ok) setResultData(await r.json())
      }
    })
    es.onerror = () => {
      // Reconnect-on-error is handled natively by EventSource; just log it once.
      setSolveLog(prev => [...prev, '[SSE] connection error — auto-retrying'])
    }
  }, [runId, selectedMethodId])

  const cancelSolve = useCallback(async () => {
    if (!runId) return
    await fetch(`${API}/cancel/${runId}`, { method: 'POST' })
  }, [runId])

  const downloadOutput = useCallback(() => {
    if (!runId) return
    window.open(`${API}/download/${runId}`, '_blank')
  }, [runId])

  const runBenchmark = useCallback(async () => {
    if (!runId) return null
    setBenchmarkData({ running: true })
    try {
      const res = await fetch(`${API}/benchmark`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: runId, sample_size: 1000, seed: 42 }),
      })
      const data = await res.json()
      setBenchmarkData(data)
      return data
    } catch (e) {
      setBenchmarkData({ error: e.message })
      return null
    }
  }, [runId])

  return (
    <Ctx.Provider value={{
      uploadStatus, uploadMeta, uploadError, uploadFile,
      runId, masterSummary,
      selectedMethodId, setSelectedMethodId,
      solveStatus, solveLog, solveStats, startSolve, cancelSolve,
      resultData, downloadOutput,
      benchmarkData, runBenchmark,
      resetAll,
    }}>
      {children}
    </Ctx.Provider>
  )
}

export const useApp = () => useContext(Ctx)
