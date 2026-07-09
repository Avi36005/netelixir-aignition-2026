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
          <span className="font-medium text-black">{file.name}</span>
        ) : (
          'Click to choose a CSV'
        )}
      </div>
    </label>
  )
}

export default function Upload({ onReady }) {
  const [google, setGoogle] = useState(null)
  const [bing, setBing] = useState(null)
  const [meta, setMeta] = useState(null)
  const [summary, setSummary] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const doUpload = async () => {
    setBusy(true)
    setErr(null)
    try {
      const res = await api.upload({ google, meta, other: bing ? [bing] : [] })
      setSummary({ ...res.summary, session_id: res.session_id })
    } catch (e) {
      setErr(
        'Upload failed: ' + e.message +
        '. Is the backend running? You can still explore with demo data below.'
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Upload ad exports</h1>
        <p className="text-neutral-500 mt-1">
          Drop your Google Ads, Microsoft/Bing Ads and Meta Ads CSVs. Channels and
          campaign types are normalized, then summarized before forecasting.
        </p>
      </div>

      <div className="flex gap-4 flex-col sm:flex-row">
        <Drop label="Google Ads CSV" file={google} onFile={setGoogle} />
        <Drop label="Microsoft / Bing Ads CSV" file={bing} onFile={setBing} />
        <Drop label="Meta Ads CSV" file={meta} onFile={setMeta} />
      </div>

      <div className="flex gap-3 items-center flex-wrap">
        <button className="btn" disabled={busy || (!google && !meta && !bing)} onClick={doUpload}>
          {busy ? 'Parsing…' : 'Parse & summarize'}
        </button>
        <button
          className="btn-outline"
          onClick={() => onReady(api.demoSession())}
          title="Explore the UI with a local demo dataset (no backend needed)"
        >
          Load demo data
        </button>
        {err && <span className="text-sm text-black border border-neutral-300 rounded px-2 py-1">{err}</span>}
      </div>

      {summary && (
        <div className="space-y-4">
          <div className="badge badge-pass">Success — files parsed</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Stat label="Rows" value={summary.rows.toLocaleString()} />
            <Stat label="Campaigns" value={summary.campaigns} />
            <Stat label="Total spend" value={fmtUSD(summary.total_spend)} />
            <Stat label="Total revenue" value={fmtUSD(summary.total_revenue)} />
          </div>
          <div className="card text-sm text-neutral-600 space-y-1">
            <div>
              <span className="label">Date range</span> {summary.date_min} →{' '}
              {summary.date_max}
            </div>
            <div>
              <span className="label">Detected channels</span>{' '}
              {summary.channels.join(', ')}
            </div>
          </div>
          {summary.by_channel && (
            <div className="card overflow-x-auto">
              <div className="label mb-3">Per-channel summary</div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-neutral-500 border-b border-neutral-200 text-xs uppercase">
                    <th className="py-2">Detected channel</th>
                    <th className="text-right">Campaigns</th>
                    <th className="text-right">Spend</th>
                    <th className="text-right">Revenue</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.by_channel.map((c) => (
                    <tr key={c.channel} className="border-b border-neutral-100">
                      <td className="py-2 capitalize">{c.channel}</td>
                      <td className="text-right">{c.campaigns}</td>
                      <td className="text-right">{fmtUSD(c.spend)}</td>
                      <td className="text-right">{fmtUSD(c.revenue)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <button
            className="btn"
            onClick={() => onReady({ session_id: summary.session_id, summary })}
          >
            Continue to validation →
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
