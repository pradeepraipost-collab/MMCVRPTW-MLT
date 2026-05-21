import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar.jsx'
import Upload from './pages/Upload.jsx'
import Configure from './pages/Configure.jsx'
import Solve from './pages/Solve.jsx'
import Results from './pages/Results.jsx'
import InputDashboard from './pages/InputDashboard.jsx'
import DataExplorer from './pages/DataExplorer.jsx'

export default function App() {
  return (
    <div className="min-h-screen">
      <Sidebar />
      <main className="ml-60 px-8 py-8">
        <Routes>
          <Route path="/" element={<InputDashboard />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/configure" element={<Configure />} />
          <Route path="/solve" element={<Solve />} />
          <Route path="/results" element={<Results />} />
          <Route path="/data" element={<DataExplorer />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
