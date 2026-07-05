import { useEffect, useState } from 'react'
import { api, fmtUSD } from '../lib/api.js'

const SEV = {
  error: 'bg-red-50 text-red-700 border-red-200',
  warning: 'bg-amber-50 text-amber-700 border-amber-200',
  info: 'bg-neutral-50 text-neutral-600 border-neutral-200',
}

export default function Validation({ session }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    api.validate(session.session_id).then(setData).catch((e) => setErr(e.message))
  }, [session.session_id])

  if (err) return <div className="card text-red-600">{err}</div>
  if (!data) return <div className="card text-neutral-400">Checking consistency…</div>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Validation report</h1>
        <p className="text-neutral-500 mt-1">
          Campaign → detected type → channel mapping, plus consistency issues.
        </p>
      </div>

      <div className={`card border ${data.ok ? 'border-neutral-200' : 'border-red-300'}`}>
        <span className="font-medium">
          {data.ok ? '✓ Data is forecast-ready' : '✗ Blocking issues found'}
        </span>
        <span className="text-neutral-400 text-sm ml-2">
          {data.issues.length} issue(s)
        </span>
      </div>

      {data.issues.length > 0 && (
        <div className="space-y-2">
          {data.issues.map((iss, i) => (
            <div key={i} className={`border rounded-md px-4 py-2 text-sm ${SEV[iss.severity]}`}>
              <span className="font-medium uppercase text-xs mr-2">{iss.severity}</span>
              {iss.message}
            </div>
          ))}
        </div>
      )}

      <div className="card overflow-x-auto">
        <div className="label mb-3">Campaign mapping</div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-neutral-500 border-b border-neutral-200 text-xs uppercase">
              <th className="py-2">Campaign</th><th>Channel</th><th>Type</th>
              <th>Brand</th><th className="text-right">Active days</th>
              <th className="text-right">Coverage</th><th className="text-right">Spend</th>
              <th className="text-right">Revenue</th>
            </tr>
          </thead>
          <tbody>
            {data.campaigns.map((c) => (
              <tr key={c.campaign} className="border-b border-neutral-100">
                <td className="py-2 max-w-xs truncate">{c.campaign}</td>
                <td className="capitalize">{c.channel}</td>
                <td>{c.campaign_type}</td>
                <td>{c.is_brand ? 'yes' : '—'}</td>
                <td className="text-right">{c.active_days}/{c.span_days}</td>
                <td className="text-right">{(c.coverage * 100).toFixed(0)}%</td>
                <td className="text-right">{fmtUSD(c.spend)}</td>
                <td className="text-right">{fmtUSD(c.revenue)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
