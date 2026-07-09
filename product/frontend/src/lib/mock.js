// Deterministic demo dataset — used ONLY when the backend is unreachable, so
// judges can still walk the UI. Clearly labeled "demo data" in the header.
// Magnitudes mirror the committed official dataset's real forecast output.

const CH = [
  { channel: 'google', spend30: 64000, roas: 4.6 },
  { channel: 'meta', spend30: 9500, roas: 5.6 },
  { channel: 'microsoft', spend30: 1800, roas: 4.9 },
]
const TYPES = {
  google: ['PerformanceMax', 'Search', 'Shopping'],
  meta: ['Prospecting', 'Retargeting'],
  microsoft: ['Search'],
}
const CAMPS = {
  google: ['PMax_AllProducts_01', 'Search_Brand_01', 'Shopping_Core_02'],
  meta: ['Prospecting_Broad_01', 'Retargeting_Cart_01'],
  microsoft: ['Search_TM_Campaign_02'],
}

function rowsFor(win) {
  const k = win / 30
  const rows = []
  let bRev = 0
  let bSpend = 0
  CH.forEach(({ channel, spend30, roas }) => {
    const spend = spend30 * k
    const p50 = spend * roas
    const r = {
      level: 'channel', channel, campaign_type: '', campaign: '', window_days: win,
      revenue_p10: p50 * 0.35, revenue_p50: p50, revenue_p90: p50 * 2.6,
      roas_p10: roas * 0.35, roas_p50: roas, roas_p90: roas * 2.6,
    }
    rows.push(r)
    bRev += p50
    bSpend += spend
    TYPES[channel].forEach((t, i) => {
      const share = [0.6, 0.3, 0.1][i] || 0.1
      rows.push({ ...r, level: 'campaign_type', campaign_type: t,
        revenue_p10: r.revenue_p10 * share, revenue_p50: p50 * share,
        revenue_p90: r.revenue_p90 * share })
      const camp = CAMPS[channel][i]
      if (camp) {
        rows.push({ ...r, level: 'campaign', campaign_type: t, campaign: camp,
          revenue_p10: r.revenue_p10 * share, revenue_p50: p50 * share,
          revenue_p90: r.revenue_p90 * share })
      }
    })
  })
  const broas = bRev / bSpend
  rows.unshift({
    level: 'blended', channel: '', campaign_type: '', campaign: '', window_days: win,
    revenue_p10: bRev * 0.35, revenue_p50: bRev, revenue_p90: bRev * 2.6,
    roas_p10: broas * 0.35, roas_p50: broas, roas_p90: broas * 2.6,
  })
  return rows
}

export const MOCK = {
  summary: {
    rows: 25562, campaigns: 109, channels: ['google', 'meta', 'microsoft'],
    date_min: '2024-01-01', date_max: '2026-06-05',
    total_spend: 2181943, total_revenue: 11095457, currency: 'USD',
    by_channel: [
      { channel: 'google', spend: 1946126, revenue: 9266678, campaigns: 71 },
      { channel: 'meta', spend: 196387, revenue: 1656751, campaigns: 15 },
      { channel: 'microsoft', spend: 39430, revenue: 172028, campaigns: 23 },
    ],
  },
  validate: {
    ok: true,
    issues: [
      { severity: 'info', code: 'other_type',
        message: 'Some rows mapped to campaign_type "Other" (name did not match a known pattern).' },
    ],
    campaigns: [],
  },
  forecast: { rows: [...rowsFor(30), ...rowsFor(60), ...rowsFor(90)] },
  simulate(scenario) {
    const channels = CH.map(({ channel, spend30, roas }) => {
      const budget = scenario[channel] ?? spend30
      const sat = 1 / (1 + budget / (spend30 * 3)) // saturating demo response
      const revenue = budget * roas * (0.7 + 0.9 * sat)
      return { channel, budget, revenue,
        roas: budget > 0 ? revenue / budget : 0, marginal_roas: roas * sat }
    })
    const budget = channels.reduce((s, c) => s + c.budget, 0)
    const revenue = channels.reduce((s, c) => s + c.revenue, 0)
    return { channels,
      blended: { budget, revenue, roas: budget > 0 ? revenue / budget : 0 } }
  },
  explain: {
    provider: 'template',
    guardrail: 'fallback',
    narrative: '',
    insights: {
      forecast_summary: [
        { claim: 'Google contributes the largest share of forecast revenue, so changes in Google spend may have the largest blended impact.',
          evidence: ['channels[google].revenue_p50'], confidence: 'high' },
        { claim: 'Meta shows the highest expected ROAS range among detected channels based on the current forecast output.',
          evidence: ['channels[meta].roas_p50'], confidence: 'medium' },
      ],
      risks: [
        { risk: 'Microsoft/Bing has lower spend volume, so the forecast confidence may be lower.',
          evidence: ['channels[microsoft]'], severity: 'medium',
          recommended_action: 'Review pacing weekly and re-forecast as new data arrives.' },
      ],
      budget_recommendations: [
        { recommendation: 'Incremental budget appears most efficient on the highest-ROAS channel, subject to diminishing returns.',
          evidence: ['channels'], expected_direction: 'increase_revenue' },
      ],
      campaigns_to_watch: [
        { campaign_or_group: 'PMax_AllProducts_01',
          reason: 'Top forecast contributor in the demo dataset.',
          evidence: ['top_campaigns'] },
      ],
      suggested_budget_shift: {
        summary: 'Based on the demo forecast output, shifting incremental budget from Google toward Meta may improve blended efficiency, subject to diminishing returns.',
        source_channel: 'google', target_channel: 'meta',
        evidence: ['channels[google].roas_p50', 'channels[meta].roas_p50'],
        confidence: 'medium',
      },
      limitations: [
        'Demo data — start the backend to see live model output.',
        'Not enough evidence in the provided data to attribute changes to external market events.',
      ],
    },
    drivers: [
      { feature: 'tr28_revenue', importance: 0.34 },
      { feature: 'budget_input', importance: 0.22 },
      { feature: 'tr28_roas', importance: 0.14 },
      { feature: 'seasonal_index', importance: 0.09 },
    ],
  },
}
