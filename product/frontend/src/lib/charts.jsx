// Tiny shared chart primitives — plain divs, monochrome, no chart library.
// Single-series bars carry identity via the row label (no legend needed);
// the two-series compare bars ship a legend (black = current, gray = simulated).

export function BarRow({ label, value, max, display, tag }) {
  const pct = max > 0 ? Math.max((value / max) * 100, 0.5) : 0
  return (
    <div className="flex items-center gap-3 text-sm">
      <div className="w-28 shrink-0 capitalize truncate">{label}</div>
      <div className="flex-1 h-4 bg-neutral-100 rounded">
        <div className="h-4 rounded bg-neutral-800" style={{ width: pct + '%' }} />
      </div>
      <div className="w-32 shrink-0 text-right tabular-nums">
        {display}{tag && <span className="text-neutral-500 text-xs"> ({tag})</span>}
      </div>
    </div>
  )
}

export function CompareBars({ label, current, simulated, display }) {
  const max = Math.max(current, simulated, 1e-9)
  const w = (v) => Math.max((v / max) * 100, 0.5) + '%'
  return (
    <div className="text-sm">
      <div className="flex justify-between mb-1">
        <span className="font-medium">{label}</span>
      </div>
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <div className="flex-1 h-3.5 bg-neutral-100 rounded">
            <div className="h-3.5 rounded bg-black" style={{ width: w(current) }} />
          </div>
          <span className="w-28 text-right tabular-nums text-xs">{display(current)}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex-1 h-3.5 bg-neutral-100 rounded">
            <div className="h-3.5 rounded bg-neutral-400" style={{ width: w(simulated) }} />
          </div>
          <span className="w-28 text-right tabular-nums text-xs">{display(simulated)}</span>
        </div>
      </div>
    </div>
  )
}

export function CompareLegend() {
  return (
    <div className="flex gap-4 text-xs text-neutral-600">
      <span className="flex items-center gap-1.5">
        <span className="inline-block w-3 h-3 rounded-sm bg-black" /> Current plan
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block w-3 h-3 rounded-sm bg-neutral-400" /> Simulated
      </span>
    </div>
  )
}

// Confidence from forecast output only: relative P10–P90 width around P50.
// Same thresholds as the blended headline card on the Forecast page.
export function confidenceOf(r) {
  if (!r || !(r.revenue_p50 > 0)) return 'Low'
  const spread = (r.revenue_p90 - r.revenue_p10) / r.revenue_p50
  if (spread < 1.5) return 'High'
  if (spread < 3.5) return 'Medium'
  return 'Low'
}

export function ConfidenceBadge({ level }) {
  const cls = level === 'High' ? 'badge badge-pass'
    : level === 'Medium' ? 'badge badge-warn' : 'badge badge-error'
  return <span className={cls}>{level}</span>
}

export function EmptyState({ message }) {
  return (
    <div className="card text-neutral-500 text-sm">
      {message || 'No forecast rows available for this selection.'}
    </div>
  )
}

// Session expiry: the backend answers 404 "Unknown session_id …" once the
// in-memory session store is gone (e.g. backend restart).
export const isSessionExpired = (e) =>
  String(e?.message || '').includes('Unknown session')
