import { useState } from 'react'
import Upload from './pages/Upload.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Simulator from './pages/Simulator.jsx'
import Breakdown from './pages/Breakdown.jsx'
import Insights from './pages/Insights.jsx'
import Validation from './pages/Validation.jsx'

const PAGES = [
  { id: 'upload', label: 'Upload' },
  { id: 'dashboard', label: 'Forecast' },
  { id: 'simulator', label: 'Budget Simulator' },
  { id: 'breakdown', label: 'Channel Breakdown' },
  { id: 'insights', label: 'AI Insights' },
  { id: 'validation', label: 'Validation Report' },
]

export default function App() {
  const [page, setPage] = useState('upload')
  const [session, setSession] = useState(null) // { session_id, summary }

  const gated = !session && page !== 'upload'

  return (
    <div className="min-h-screen">
      <header className="border-b border-neutral-200 bg-white sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center gap-6">
          <div className="font-bold text-lg tracking-tight">
            ROAS<span className="text-neutral-400">cast</span>
          </div>
          <nav className="flex gap-1 flex-wrap">
            {PAGES.map((p) => (
              <button
                key={p.id}
                disabled={!session && p.id !== 'upload'}
                className={`tab ${page === p.id ? 'tab-active' : 'tab-idle'} disabled:opacity-30`}
                onClick={() => setPage(p.id)}
              >
                {p.label}
              </button>
            ))}
          </nav>
          {session && (
            <div className="ml-auto text-xs text-neutral-400">
              session {session.session_id}
            </div>
          )}
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        {gated ? (
          <div className="card text-center text-neutral-500">
            Upload your Google &amp; Meta CSVs first to run a forecast.
          </div>
        ) : (
          <>
            {page === 'upload' && (
              <Upload
                onReady={(s) => {
                  setSession(s)
                  setPage('dashboard')
                }}
              />
            )}
            {page === 'dashboard' && <Dashboard session={session} />}
            {page === 'simulator' && <Simulator session={session} />}
            {page === 'breakdown' && <Breakdown session={session} />}
            {page === 'insights' && <Insights session={session} />}
            {page === 'validation' && <Validation session={session} />}
          </>
        )}
      </main>

      <footer className="max-w-6xl mx-auto px-6 py-6 text-xs text-neutral-400">
        Probabilistic revenue &amp; ROAS forecasts · all amounts USD · ROAS is a
        dimensionless multiple · forecasts are 30/60/90-day window totals (never daily).
      </footer>
    </div>
  )
}
