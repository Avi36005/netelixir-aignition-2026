import { useState } from 'react'
import { api, fmtUSD } from '../lib/api.js'

function Drop({ label, file, onFile }) {
  return (
    <label className="card flex-1 cursor-pointer hover:border-neutral-400 transition block">
      <div className="label mb-2">{label}</div>
      <input
        type="file"
        accept=".csv"
        className="hidden"
        onChange={(e) => onFile(e.target.files[0])}
      />
      <div className="text-sm text-neutral-600">
        {file ? (
          <span className="font-medium text-neutral-900">{file.name}</span>
        ) : (
          'Click to choose a CSV'
        )}
      </div>
    </label>
  )
}

export default function Upload({ onReady }) {
  const [google, setGoogle] = useState(null)
  const [meta, setMeta] = useState(null)
  const [summary, setSummary] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const doUpload = async () => {
    setBusy(true)
    setErr(null)
    try {
      const res = await api.upload({ google, meta })
      setSummary({ ...res.summary, session_id: res.session_id })
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Upload ad exports</h1>
        <p className="text-neutral-500 mt-1">
          Drop your Google Ads and Meta Ads CSVs. We normalize channels &amp;
          campaign types, then summarize before forecasting.
        </p>
      </div>

      <div className="flex gap-4 flex-col sm:flex-row">
        <Drop label="Google Ads CSV" file={google} onFile={setGoogle} />
        <Drop label="Meta Ads CSV" file={meta} onFile={setMeta} />
      </div>

      <div className="flex gap-3 items-center">
        <button className="btn" disabled={busy || (!google && !meta)} onClick={doUpload}>
          {busy ? 'Parsing…' : 'Parse & summarize'}
        </button>
        {err && <span className="text-sm text-red-600">{err}</span>}
      </div>

      {summary && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Stat label="Rows" value={summary.rows.toLocaleString()} />
            <Stat label="Campaigns" value={summary.campaigns} />
            <Stat label="Total spend" value={fmtUSD(summary.total_spend)} />
            <Stat label="Total revenue" value={fmtUSD(summary.total_revenue)} />
          </div>
          <div className="card text-sm text-neutral-600">
            <div>
              <span className="label">Date range</span> {summary.date_min} →{' '}
              {summary.date_max}
            </div>
            <div className="mt-1">
              <span className="label">Channels</span> {summary.channels.join(', ')}
            </div>
          </div>
          <button
            className="btn"
            onClick={() => onReady({ session_id: summary.session_id, summary })}
          >
            Run forecast →
          </button>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className="metric mt-1">{value}</div>
    </div>
  )
}
