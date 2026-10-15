const OTHER_LABEL = 'Прочие';
const MS_PER_YEAR = 365.25 * 86_400_000;

export const quarterOf = (date) =>
  `${date.getUTCFullYear()} Q${Math.floor(date.getUTCMonth() / 3) + 1}`;

export const monthOf = (date) =>
  `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`;

const round = (value) => Math.round(value * 100) / 100;

/** Sums `valueOf(row)` per `keyOf(row)`; returns entries sorted by key. */
function sumBy(rows, keyOf, valueOf) {
  const totals = rows.reduce((acc, row) => {
    const key = keyOf(row);
    return acc.set(key, (acc.get(key) ?? 0) + valueOf(row));
  }, new Map());
  return [...totals.entries()].sort(([a], [b]) => a.localeCompare(b, 'ru'));
}

const byValueDesc = (a, b) => b.value - a.value;
const toItems = (entries) => entries.map(([name, value]) => ({ name, value: round(value) }));
const uniqueSorted = (values) => [...new Set(values)].filter(Boolean).sort((a, b) => a.localeCompare(b, 'ru'));

export function buildFilterOptions({ collections, prolongations }) {
  const all = [...collections, ...prolongations];
  return {
    groups: uniqueSorted(all.map((r) => r.group)),
    branches: uniqueSorted(all.map((r) => r.branch)),
    agents: uniqueSorted(all.map((r) => r.agent)),
    lines: uniqueSorted(all.map((r) => r.line)),
    years: uniqueSorted(collections.map((r) => String(r.period.getUTCFullYear()))),
  };
}

function matches(row, filters, dateOf) {
  if (filters.group && row.group !== filters.group) return false;
  if (filters.branch && row.branch !== filters.branch) return false;
  if (filters.agent && row.agent !== filters.agent) return false;
  if (filters.line && row.line !== filters.line) return false;
  if (filters.year) {
    const date = dateOf(row);
    if (!date || String(date.getUTCFullYear()) !== filters.year) return false;
  }
  return true;
}

function kpi(collections, prolongations) {
  const total = collections.reduce((sum, r) => sum + r.amount, 0);
  const refunds = collections.filter((r) => r.amount < 0).reduce((sum, r) => sum + r.amount, 0);
  const contracts = new Set(collections.map((r) => r.contract)).size;
  return {
    total: round(total),
    refunds: round(refunds),
    contracts,
    avgPerContract: contracts ? round(total / contracts) : 0,
    prolongationsDue: prolongations.length,
  };
}

/** Quarter × line matrix keeping the top `limit` lines and folding the rest into «Прочие». */
function quarterByLine(collections, limit) {
  const quarters = uniqueSorted(collections.map((r) => quarterOf(r.period)));
  const lineTotals = toItems(sumBy(collections, (r) => r.line, (r) => r.amount)).sort(byValueDesc);
  const kept = new Set(lineTotals.slice(0, limit).map((l) => l.name));
  const hasOther = lineTotals.length > limit;
  const lineOf = (r) => (kept.has(r.line) ? r.line : OTHER_LABEL);

  const cells = new Map(sumBy(collections, (r) => `${lineOf(r)}|${quarterOf(r.period)}`, (r) => r.amount));
  const names = [...lineTotals.slice(0, limit).map((l) => l.name), ...(hasOther ? [OTHER_LABEL] : [])];
  return {
    quarters,
    series: names.map((name) => ({
      name,
      values: quarters.map((q) => round(cells.get(`${name}|${q}`) ?? 0)),
    })),
  };
}

function agentQuarterHeatmap(collections) {
  const quarters = uniqueSorted(collections.map((r) => quarterOf(r.period)));
  const agents = uniqueSorted(collections.map((r) => r.agent));
  const cells = new Map(sumBy(collections, (r) => `${r.agent}|${quarterOf(r.period)}`, (r) => r.amount));
  const values = agents.flatMap((agent, ai) =>
    quarters.map((q, qi) => [qi, ai, round(cells.get(`${agent}|${q}`) ?? 0)]),
  );
  return { quarters, agents, values };
}

function agentTenure(agents, collections, now) {
  const totals = new Map(sumBy(collections, (r) => r.agent, (r) => r.amount));
  return agents
    .filter((a) => a.firstContractDate && totals.has(a.name))
    .map((a) => ({
      name: a.name,
      years: round((now - a.firstContractDate) / MS_PER_YEAR),
      value: round(totals.get(a.name)),
    }));
}

export function buildDashboard(dataset, filters, now = new Date()) {
  const collections = dataset.collections.filter((r) => r.period && matches(r, filters, (x) => x.period));
  const prolongations = dataset.prolongations.filter((r) => matches(r, filters, (x) => x.endAt));
  const count = () => 1;

  return {
    kpi: kpi(collections, prolongations),
    byQuarter: toItems(sumBy(collections, (r) => quarterOf(r.period), (r) => r.amount)),
    byQuarterLine: quarterByLine(collections, 5),
    byAgent: toItems(sumBy(collections, (r) => r.agent, (r) => r.amount)).sort(byValueDesc),
    byBranch: toItems(sumBy(collections, (r) => r.branch, (r) => r.amount)).sort(byValueDesc),
    byGroup: toItems(sumBy(collections, (r) => r.group, (r) => r.amount)).sort(byValueDesc),
    topProducts: toItems(sumBy(collections, (r) => r.product, (r) => r.amount)).sort(byValueDesc).slice(0, 10),
    agentQuarterHeatmap: agentQuarterHeatmap(collections),
    agentTenure: agentTenure(dataset.agents, collections, now),
    prolongByMonth: toItems(sumBy(prolongations.filter((r) => r.endAt), (r) => monthOf(r.endAt), count)),
    prolongByAgent: toItems(sumBy(prolongations, (r) => r.agent, count)).sort(byValueDesc),
    prolongByProduct: toItems(sumBy(prolongations, (r) => r.product, count)).sort(byValueDesc),
  };
}
