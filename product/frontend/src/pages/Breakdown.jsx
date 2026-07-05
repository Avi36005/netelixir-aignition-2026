import { useEffect, useMemo, useState } from 'react'
import { api, fmtUSD, fmtROAS } from '../lib/api.js'

const WINDOWS = [30, 60, 90]

export default function Breakdown({ session }) {
  const [win, setWin] = useState(30)
  const [rows, setRows] = useState(null)
  const [expanded, setExpanded] = useState({})
  const [err, setErr] = useState(null)

  useEffect(() => {
    api.forecast(session.session_id, null).then((r) => setRows(r.rows)).catch((e) => setErr(e.message))
  }, [session.session_id])

  const tree = useMemo(() => {
    if (!rows) return null
    const r = rows.filter((x) => Number(x.window_days) === win)
    const channels = r.filter((x) => x.level === 'channel')
    const types = r.filter((x) => x.level === 'campaign_type')
    const camps = r.filter((x) => x.level === 'campaign')
    return channels
      .sort((a, b) => b.revenue_p50 - a.revenue_p50)
      .map((ch) => ({
        ...ch,
        types: types
          .filter((t) => t.channel === ch.channel)
          .sort((a, b) => b.revenue_p50 - a.revenue_p50)
          .map((t) => ({
            ...t,
            campaigns: camps
              .filter((c) => c.channel === ch.channel && c.campaign_type === t.campaign_type)
              .sort((a, b) => b.revenue_p50 - a.revenue_p50),
          })),
      }))
  }, [rows, win])

  if (err) return <div className="card text-red-600">{err}</div>
  if (!tree) return <div className="card text-neutral-400">Loading…</div>

  const toggle = (k) => setExpanded((e) => ({ ...e, [k]: !e[k] }))

  const Row = ({ d, depth, label }) => (
    <tr className="border-b border-neutral-100 hover:bg-neutral-50">
      <td className="py-2" style={{ paddingLeft: depth * 18 + 8 }}>{label}</td>
      <td className="text-right tabular-nums">{fmtUSD(d.revenue_p10)}</td>
      <td className="text-right tabular-nums font-medium">{fmtUSD(d.revenue_p50)}</td>
      <td className="text-right tabular-nums">{fmtUSD(d.revenue_p90)}</td>
      <td className="text-right tabular-nums">{fmtROAS(d.roas_p10)}</td>
      <td className="text-right tabular-nums font-medium">{fmtROAS(d.roas_p50)}</td>
      <td className="text-right tabular-nums">{fmtROAS(d.roas_p90)}</td>
    </tr>
  )

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Channel breakdown</h1>
        <div className="flex gap-1 bg-neutral-100 p-1 rounded-md">
          {WINDOWS.map((w) => (
            <button key={w} className={`tab ${win === w ? 'tab-active' : 'tab-idle'}`}
              onClick={() => setWin(w)}>{w}d</button>
          ))}
        </div>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-neutral-500 border-b border-neutral-200 text-xs uppercase">
              <th className="text-left py-2">Channel → Type → Campaign</th>
              <th className="text-right">Rev P10</th>
              <th className="text-right">Rev P50</th>
              <th className="text-right">Rev P90</th>
              <th className="text-right">ROAS P10</th>
              <th className="text-right">ROAS P50</th>
              <th className="text-right">ROAS P90</th>
            </tr>
          </thead>
          <tbody>
            {tree.map((ch) => {
              const ck = 'c:' + ch.channel
              return (
                <FragmentRows key={ck}>
                  <tr className="border-b border-neutral-200 bg-neutral-50 cursor-pointer font-semibold"
                    onClick={() => toggle(ck)}>
                    <td className="py-2 pl-2 capitalize">
                      {expanded[ck] ? '▾' : '▸'} {ch.channel}
                    </td>
                    <td className="text-right">{fmtUSD(ch.revenue_p10)}</td>
                    <td className="text-right">{fmtUSD(ch.revenue_p50)}</td>
                    <td className="text-right">{fmtUSD(ch.revenue_p90)}</td>
                    <td className="text-right">{fmtROAS(ch.roas_p10)}</td>
                    <td className="text-right">{fmtROAS(ch.roas_p50)}</td>
                    <td className="text-right">{fmtROAS(ch.roas_p90)}</td>
                  </tr>
                  {expanded[ck] && ch.types.map((t) => {
                    const tk = ck + '/' + t.campaign_type
                    return (
                      <FragmentRows key={tk}>
                        <tr className="border-b border-neutral-100 cursor-pointer"
                          onClick={() => toggle(tk)}>
                          <td className="py-2" style={{ paddingLeft: 26 }}>
                            {t.campaigns.length ? (expanded[tk] ? '▾' : '▸') : '•'}{' '}
                            {t.campaign_type}
                          </td>
                          <td className="text-right">{fmtUSD(t.revenue_p10)}</td>
                          <td className="text-right font-medium">{fmtUSD(t.revenue_p50)}</td>
                          <td className="text-right">{fmtUSD(t.revenue_p90)}</td>
                          <td className="text-right">{fmtROAS(t.roas_p10)}</td>
                          <td className="text-right font-medium">{fmtROAS(t.roas_p50)}</td>
                          <td className="text-right">{fmtROAS(t.roas_p90)}</td>
                        </tr>
                        {expanded[tk] && t.campaigns.map((c) => (
                          <Row key={c.campaign} d={c} depth={3} label={c.campaign} />
                        ))}
                      </FragmentRows>
                    )
                  })}
                </FragmentRows>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-neutral-400">
        Numbers are coherent across levels: campaign sums to type sums to channel
        sums to the blended total.
      </p>
    </div>
  )
}

function FragmentRows({ children }) {
  return <>{children}</>
}
