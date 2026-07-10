import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { isSessionExpired } from '../lib/charts.jsx'

const WINDOWS = [30, 60, 90]

function Section({ title, children }) {
  return (
    <div className="card">
      <div className="label mb-3">{title}</div>
      {children}
    </div>
  )
}

function Items({ list, render, empty }) {
  if (!list || list.length === 0) {
    return <p className="text-sm text-neutral-500">{empty}</p>
  }
  return (
    <ul className="space-y-2 text-sm leading-relaxed list-disc pl-5">
      {list.map((x, i) => <li key={i}>{render(x)}</li>)}
    </ul>
  )
}

export default function Insights({ session, onExpired }) {
  const [win, setWin] = useState(30)
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const load = (w) => {
    setBusy(true)
    setErr(null)
    api.explain(session.session_id, w)
      .then(setData)
      .catch((e) => (isSessionExpired(e) ? onExpired?.() : setErr(e.message)))
      .finally(() => setBusy(false))
  }

  useEffect(() => { load(win) }, [win, session.session_id])

  const ins = data?.insights
  const shift = ins?.suggested_budget_shift
  const providerName = data?.provider === 'template' ? 'Rule-based fallback' : data?.provider

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">AI insights</h1>
          <p className="text-neutral-500 mt-1">
            Every statement is grounded in the forecast output — numbers are never
            invented by the AI.
          </p>
        </div>
        <div className="flex gap-1 border border-neutral-200 p-1 rounded-md">
          {WINDOWS.map((w) => (
            <button key={w} className={`tab ${win === w ? 'tab-active' : 'tab-idle'}`}
              onClick={() => setWin(w)}>{w}d</button>
          ))}
        </div>
      </div>

      {err && <div className="card">Error: {err}</div>}
      {busy && <div className="card text-neutral-400">Generating insights…</div>}

      {!busy && data && (
        <>
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex gap-2">
              <span className="badge badge-pass">AI provider: {providerName}</span>
              <span className={data.guardrail === 'passed' ? 'badge badge-pass' : 'badge badge-warn'}>
                Guardrail: {data.guardrail === 'passed' ? 'Passed' : 'Fallback used'}
              </span>
            </div>
            <button className="btn-outline" onClick={() => load(win)}>Regenerate</button>
          </div>

          <p className="text-xs text-neutral-500">
            AI insights are grounded in model-generated forecast outputs. The LLM
            does not generate forecast numbers.
          </p>

          {data.provider === 'template' && (
            <div className="card text-sm">
              AI insights are unavailable. Showing rule-based summary from
              forecast output.
            </div>
          )}

          {ins ? (
            <div className="space-y-4">
              <Section title="Forecast summary">
                <Items list={ins.forecast_summary} empty="Not enough evidence in the provided data."
                  render={(x) => <>
                    {x.claim}{' '}
                    <span className="text-xs text-neutral-500">({x.confidence} confidence)</span>
                  </>} />
              </Section>

              <Section title="Anomalies & risks">
                <Items list={ins.risks} empty="No risks flagged in the current forecast output."
                  render={(x) => <>
                    {x.risk}{' '}
                    <span className="text-xs text-neutral-500">[{x.severity}]</span>
                    {x.recommended_action && (
                      <div className="text-xs text-neutral-500 mt-1">
                        Action: {x.recommended_action}
                      </div>
                    )}
                  </>} />
              </Section>

              <Section title="Budget recommendation">
                <Items list={ins.budget_recommendations}
                  empty="Not enough evidence in the provided data."
                  render={(x) => x.recommendation} />
              </Section>

              <Section title="Campaigns to watch">
                <Items list={ins.campaigns_to_watch}
                  empty="No campaigns flagged."
                  render={(x) => <><b>{x.campaign_or_group}</b> — {x.reason}</>} />
              </Section>

              <Section title="Suggested budget shift">
                {shift && shift.summary ? (
                  <div className="text-sm leading-relaxed">
                    <p>{shift.summary}</p>
                    {(shift.source_channel || shift.target_channel) && (
                      <p className="text-xs text-neutral-500 mt-1 capitalize">
                        {shift.source_channel || '—'} → {shift.target_channel || '—'}
                        {' '}({shift.confidence} confidence)
                      </p>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-neutral-500">
                    Not enough evidence in the provided data for a directional shift.
                  </p>
                )}
              </Section>

              <Section title="Limitations">
                <Items list={ins.limitations} empty="—" render={(x) => x} />
              </Section>
            </div>
          ) : (
            data.narrative && (
              <div className="card text-sm whitespace-pre-wrap">{data.narrative}</div>
            )
          )}

          {data.drivers?.length > 0 && (
            <Section title="Top model drivers (grounding the insights)">
              <div className="space-y-2">
                {data.drivers.map((d) => (
                  <div key={d.feature} className="flex items-center gap-3">
                    <span className="w-40 text-sm text-neutral-600">{d.feature}</span>
                    <div className="flex-1 bg-neutral-100 rounded h-2">
                      <div className="bg-black h-2 rounded"
                        style={{ width: `${Math.min(d.importance * 100, 100)}%` }} />
                    </div>
                    <span className="text-xs text-neutral-500 w-12 text-right">
                      {(d.importance * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            </Section>
          )}
        </>
      )}
    </div>
  )
}
