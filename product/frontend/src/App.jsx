import { useState } from 'react'
import Upload from './pages/Upload.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Simulator from './pages/Simulator.jsx'
import Breakdown from './pages/Breakdown.jsx'
import Insights from './pages/Insights.jsx'
import Validation from './pages/Validation.jsx'

const PAGES = [
  { id: 'upload', label: 'Upload' },
  { id: 'validation', label: 'Validation' },
  { id: 'dashboard', label: 'Forecast' },
  { id: 'breakdown', label: 'Channel Breakdown' },
  { id: 'simulator', label: 'Budget Simulator' },
  { id: 'insights', label: 'AI Insights' },
]

export default function App() {
  const [page, setPage] = useState('upload')
  const [session, setSession] = useState(null) // { session_id, summary, mock? }

  // Expired/unknown session (backend restarted) -> back to Upload.
  const onExpired = () => { setSession(null); setPage('upload') }

  return (
    <div className="min-h-screen bg-white text-black flex flex-col">
      <header className="border-b border-neutral-200 bg-white">
        <div className="px-6 py-3 flex items-center justify-between">
          <div className="font-bold text-lg tracking-tight text-black">
            ROAS<span className="text-neutral-400">cast</span>
            <span className="ml-3 text-xs font-normal text-neutral-500">
              Probabilistic revenue &amp; ROAS forecasting
            </span>
          </div>
          {session && (
            <div className="text-xs text-neutral-500">
              session {session.session_id}
              {session.mock ? ' · demo data (backend offline)' : ''}
            </div>
          )}
        </div>
      </header>

      <div className="flex flex-1">
        <aside className="w-56 shrink-0 border-r border-neutral-200 bg-white p-3 space-y-1">
          {PAGES.map((p) => (
            <button
              key={p.id}
              disabled={!session && p.id !== 'upload'}
              className={`nav-item ${page === p.id ? 'nav-active' : ''}`}
              onClick={() => setPage(p.id)}
            >
              {p.label}
            </button>
          ))}
        </aside>

        <main className="flex-1 px-8 py-8 max-w-5xl">
          {page === 'upload' && (
            <Upload onReady={(s) => { setSession(s); setPage('validation') }} />
          )}
          {page === 'validation' && session && <Validation session={session} onExpired={onExpired} />}
          {page === 'dashboard' && session && <Dashboard session={session} onExpired={onExpired} />}
          {page === 'breakdown' && session && <Breakdown session={session} onExpired={onExpired} />}
          {page === 'simulator' && session && <Simulator session={session} onExpired={onExpired} />}
          {page === 'insights' && session && <Insights session={session} onExpired={onExpired} />}
        </main>
      </div>

      <footer className="border-t border-neutral-200 px-6 py-4 text-xs text-neutral-500">
        All amounts USD · ROAS is a dimensionless multiple (e.g. 5.2x) · every
        forecast is a 30/60/90-day window total (never daily) · P10 = low estimate,
        P50 = expected, P90 = high estimate.
      </footer>
    </div>
  )
}
