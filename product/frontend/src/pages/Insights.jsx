import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'

const WINDOWS = [30, 60, 90]

// Minimal markdown -> JSX: **bold**, _italic_, and section headers.
function render(text) {
  return text.split('\n\n').map((block, i) => {
    const html = block
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/_(.+?)_/g, '<em class="text-neutral-500">$1</em>')
    return (
      <p key={i} className="mb-3 leading-relaxed text-sm"
        dangerouslySetInnerHTML={{ __html: html }} />
    )
  })
}

export default function Insights({ session }) {
  const [win, setWin] = useState(30)
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const load = (w) => {
    setBusy(true)
    setErr(null)
    api.explain(session.session_id, w)
      .then(setData)
      .catch((e) => setErr(e.message))
      .finally(() => setBusy(false))
  }

  useEffect(() => { load(win) }, [win, session.session_id])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">AI insights</h1>
          <p className="text-neutral-500 mt-1">
            A grounded narrative over the forecast — uses the model's real numbers
            and top drivers, never invented figures.
          </p>
        </div>
        <div className="flex gap-1 bg-neutral-100 p-1 rounded-md">
          {WINDOWS.map((w) => (
            <button key={w} className={`tab ${win === w ? 'tab-active' : 'tab-idle'}`}
              onClick={() => setWin(w)}>{w}d</button>
          ))}
        </div>
      </div>

      {err && <div className="card text-red-600">{err}</div>}

      <div className="card min-h-[200px]">
        {busy ? (
          <div className="text-neutral-400">Generating narrative…</div>
        ) : data ? (
          <>
            <div className="flex items-center justify-between mb-4">
              <span className="text-xs px-2 py-1 rounded bg-neutral-100 text-neutral-600">
                provider: {data.provider}
              </span>
              <button className="btn-ghost border border-neutral-200" onClick={() => load(win)}>
                ↻ Regenerate
              </button>
            </div>
            {render(data.narrative)}
          </>
        ) : null}
      </div>

      {data?.drivers?.length > 0 && (
        <div className="card">
          <div className="label mb-3">Top model drivers (grounding the narrative)</div>
          <div className="space-y-2">
            {data.drivers.map((d) => (
              <div key={d.feature} className="flex items-center gap-3">
                <span className="w-40 text-sm text-neutral-600">{d.feature}</span>
                <div className="flex-1 bg-neutral-100 rounded h-2">
                  <div className="bg-neutral-900 h-2 rounded"
                    style={{ width: `${Math.min(d.importance * 100, 100)}%` }} />
                </div>
                <span className="text-xs text-neutral-400 w-12 text-right">
                  {(d.importance * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
