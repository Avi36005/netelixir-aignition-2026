import { useEffect, useState } from 'react'
import { api, fmtUSD } from '../lib/api.js'
import { isSessionExpired } from '../lib/charts.jsx'

function Badge({ status }) {
  const cls = status === 'Pass' ? 'badge badge-pass'
    : status === 'Warning' ? 'badge badge-warn' : 'badge badge-error'
  return <span className={cls}>{status}</span>
}

function CheckRow({ label, status, detail }) {
  return (
    <tr className="border-b border-neutral-100">
      <td className="py-2">{label}</td>
      <td><Badge status={status} /></td>
      <td className="text-neutral-500 text-sm">{detail}</td>
    </tr>
  )
}

export default function Validation({ session, onExpired }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    api.validate(session.session_id).then(setData)
      .catch((e) => (isSessionExpired(e) ? onExpired?.() : setErr(e.message)))
  }, [session.session_id])

  if (err) return <div className="card">Error: {err}</div>
  if (!data) return <div className="card text-neutral-400">Checking consistency…</div>

  const s = session.summary || {}
  const channels = s.channels || []
  const byCh = Object.fromEntries((s.by_channel || []).map((c) => [c.channel, c]))
  const has = (ch) => channels.includes(ch)
  const zeroRev = (ch) => byCh[ch] && byCh[ch].revenue === 0
  const otherRows = byCh.other ? byCh.other.campaigns : 0
  const warnings = data.issues.filter((i) => i.severity === 'warning').length
  const errors = data.issues.filter((i) => i.severity === 'error').length

  const checks = [
    { label: 'Google data detected', status: has('google') ? 'Pass' : 'Warning',
      detail: has('google') ? `${fmtUSD(byCh.google?.spend)} spend parsed` : 'No google rows found' },
    { label: 'Microsoft/Bing data detected', status: has('microsoft') ? 'Pass' : 'Warning',
      detail: has('microsoft') ? `${fmtUSD(byCh.microsoft?.spend)} spend parsed` : 'No microsoft rows found' },
    { label: 'Meta data detected', status: has('meta') ? 'Pass' : 'Warning',
      detail: has('meta') ? `${fmtUSD(byCh.meta?.spend)} spend parsed` : 'No meta rows found' },
    { label: 'Unmapped channel rows (channel = other)',
      status: byCh.other ? 'Warning' : 'Pass',
      detail: byCh.other ? `${otherRows} campaign(s) unmapped — must stay ≤ 5% of rows` : 'None — 0%' },
    { label: 'Invalid date rows', status: 'Pass',
      detail: 'Rows with unparseable dates are dropped automatically at ingestion' },
    { label: 'Revenue fields present', status: (s.total_revenue ?? 0) > 0 ? 'Pass' : 'Error',
      detail: (s.total_revenue ?? 0) > 0 ? `${fmtUSD(s.total_revenue)} total revenue parsed`
        : 'Total revenue is zero — check revenue column mapping' },
    { label: 'Spend fields present', status: (s.total_spend ?? 0) > 0 ? 'Pass' : 'Error',
      detail: (s.total_spend ?? 0) > 0 ? `${fmtUSD(s.total_spend)} total spend parsed`
        : 'Total spend is zero — check spend column mapping' },
    ...channels.filter((c) => c !== 'other').map((ch) => ({
      label: `${ch} parsed rows`, status: zeroRev(ch) ? 'Warning' : 'Pass',
      detail: zeroRev(ch) ? 'Channel present but revenue is zero' : 'Rows and revenue parsed',
    })),
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Validation report</h1>
        <p className="text-neutral-500 mt-1">
          Ingestion checks plus campaign → type → channel mapping consistency.
        </p>
      </div>

      <div className="card">
        <span className="font-medium">
          {data.ok ? 'Data is forecast-ready' : 'Blocking issues found'}
        </span>
        <span className="text-neutral-500 text-sm ml-2">
          {errors} error(s), {warnings} warning(s)
        </span>
      </div>

      {data.scale && (
        <div className="card">
          <div className="label mb-3">Training-scale comparison (OOD guard)</div>
          <div className="flex items-center gap-3 mb-2">
            <Badge status={data.scale.confidence === 'High' ? 'Pass'
              : data.scale.confidence === 'Medium' ? 'Warning' : 'Error'} />
            <span className="text-sm">
              Forecast confidence: <b>{data.scale.confidence}</b>
              {' '}· OOD score {Number(data.scale.ood_score).toFixed(2)}
              {' '}· fallback {data.scale.fallback_used ? 'yes' : 'no'}
              {' '}(model {Math.round(data.scale.model_weight * 100)}% /
              baseline {Math.round(data.scale.baseline_weight * 100)}%)
            </span>
          </div>
          {data.scale.warning && (
            <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-3 py-2 mb-2">
              {data.scale.warning}
            </p>
          )}
          {data.scale.reasons?.length > 0 && (
            <ul className="text-sm text-neutral-600 list-disc ml-5 space-y-1">
              {data.scale.reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          )}
          {data.scale.comparison && (
            <table className="w-full text-sm mt-3">
              <thead>
                <tr className="text-left text-neutral-500 border-b border-neutral-200 text-xs uppercase">
                  <th className="py-2">Metric</th>
                  <th className="text-right">Uploaded (median)</th>
                  <th className="text-right">Training (median)</th>
                  <th className="text-right">Ratio</th>
                </tr>
              </thead>
              <tbody>
                {['monthly_spend', 'monthly_revenue', 'campaign_monthly_spend',
                  'campaign_monthly_revenue'].map((k) => {
                  const c = data.scale.comparison[k]
                  if (!c) return null
                  return (
                    <tr key={k} className="border-b border-neutral-100">
                      <td className="py-2">{k.replaceAll('_', ' ')}</td>
                      <td className="text-right">{fmtUSD(c.uploaded_p50)}</td>
                      <td className="text-right">{fmtUSD(c.training_p50)}</td>
                      <td className="text-right">
                        {c.ratio_vs_training_median == null ? '—' : c.ratio_vs_training_median + 'x'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      <div className="card overflow-x-auto">
        <div className="label mb-3">Checks</div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-neutral-500 border-b border-neutral-200 text-xs uppercase">
              <th className="py-2">Check</th><th>Status</th><th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {checks.map((c) => <CheckRow key={c.label} {...c} />)}
          </tbody>
        </table>
      </div>

      {data.issues.length > 0 && (
        <div className="card">
          <div className="label mb-3">Issues</div>
          <div className="space-y-2">
            {data.issues.map((iss, i) => (
              <div key={i} className="border border-neutral-200 rounded-md px-4 py-2 text-sm flex gap-2 items-start">
                <Badge status={iss.severity === 'error' ? 'Error'
                  : iss.severity === 'warning' ? 'Warning' : 'Pass'} />
                <span>{iss.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.campaigns?.length > 0 && (
        <div className="card overflow-x-auto">
          <div className="label mb-3">Campaign mapping (top by spend)</div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-neutral-500 border-b border-neutral-200 text-xs uppercase">
                <th className="py-2">Campaign</th><th>Channel</th><th>Type</th>
                <th className="text-right">Active days</th>
                <th className="text-right">Spend</th>
                <th className="text-right">Revenue</th>
              </tr>
            </thead>
            <tbody>
              {data.campaigns.slice(0, 25).map((c) => (
                <tr key={c.campaign} className="border-b border-neutral-100">
                  <td className="py-2 max-w-xs truncate">{c.campaign}</td>
                  <td className="capitalize">{c.channel}</td>
                  <td>{c.campaign_type}</td>
                  <td className="text-right">{c.active_days}/{c.span_days}</td>
                  <td className="text-right">{fmtUSD(c.spend)}</td>
                  <td className="text-right">{fmtUSD(c.revenue)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
