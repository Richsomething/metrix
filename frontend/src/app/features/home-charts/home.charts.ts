import { ChartTokens } from '../../core/services/theme.service';
import { KvRecommendations } from '../../core/models/kv.model';
import { ChartView } from '../../shared/components/chart-card/chart-card.component';
import { formatCompact, formatInteger } from '../../shared/utils/format';
import {
  RADIUS,
  baseOption,
  categoryAxis,
  horizontalBars,
  legend,
  valueAxis,
} from '../dashboard/chart-options/base';

const pctFormat = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 });
const pct = (value: number | null): string =>
  value === null ? '—' : `${pctFormat.format(value * 100)}%`;
const money = (value: number): string => `${formatInteger(value)} ₽`;

/** «1 договор», «3 договора», «5 договоров». */
function contractsWord(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'договор';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'договора';
  return 'договоров';
}

/** «2026Q4» → «2026Q3». */
function previousQuarter(quarter: string): string {
  const [year, q] = quarter.split('Q').map(Number);
  return q === 1 ? `${year - 1}Q4` : `${year}Q${q - 1}`;
}

/**
 * АВ rates by line as horizontal bars, readable without the table: every bar says its rate, how many contracts it
 * stands on and from which quarter (quarter T's rate comes from the sales of T−1); the target also says its gain.
 */
export function ratesChart(r: KvRecommendations, t: ChartTokens): ChartView {
  const reporting = previousQuarter(r.quarter);
  const series = [
    {
      name: `${r.quarter} — действует сейчас`,
      color: t.series[1],
      rates: r.rates.map((x) => x.current),
      contracts: r.rates.map((x) => x.contracts.current),
      source: `за ${reporting}`,
      estimate: false,
    },
    {
      name: `${r.nextQuarter} — прогноз при текущих продажах`,
      color: t.series[2],
      rates: r.rates.map((x) => x.next),
      contracts: r.rates.map((x) => x.contracts.next),
      source: `за ${r.quarter}`,
      estimate: true,
    },
    {
      name: `${r.nextQuarter} — цель, максимальный вариант`,
      color: t.series[3],
      rates: r.rates.map((x) => x.nextWithPlan),
      contracts: r.rates.map((x) => x.contracts.nextWithPlan),
      source: `за ${r.quarter}`,
      estimate: true,
    },
  ];
  const describe = (s: (typeof series)[number], i: number): string => {
    const n = s.contracts[i];
    return `${s.estimate ? '≈ ' : ''}${formatInteger(n)} ${contractsWord(n)} ${s.source}`;
  };
  const extra = (s: (typeof series)[number], i: number): string => {
    if (s !== series[2]) return '';
    const parts = [];
    const forecast = series[1].rates[i];
    const target = s.rates[i];
    if (forecast !== null && target !== null)
      parts.push(`+${pctFormat.format(Math.max(0, target - forecast) * 100)} п.п.`);
    if (r.rates[i].cappedWithPlan) parts.push('выше нельзя');
    return parts.join(', ');
  };
  return {
    option: {
      ...baseOption(t),
      grid: { left: 8, right: 330, top: 64, bottom: 8, containLabel: true },
      legend: { ...legend(t), orient: 'vertical' },
      tooltip: {
        ...baseOption(t).tooltip,
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: unknown) => {
          const items = params as { dataIndex: number; seriesIndex: number; marker: string }[];
          const i = items[0].dataIndex;
          const lines = items.map((p) => {
            const s = series[p.seriesIndex];
            const gain = extra(s, i);
            return `${p.marker}${s.name}: <b>${pct(s.rates[i])}</b> · ${describe(s, i)}${gain ? ` · ${gain}` : ''}`;
          });
          return [`<b>${r.rates[i].title}</b>`, ...lines].join('<br>');
        },
      },
      xAxis: {
        ...valueAxis(t, (v) => pct(v)),
        max: (v: { max: number }) => Math.ceil(v.max * 10) / 10,
      },
      yAxis: {
        ...categoryAxis(
          t,
          r.rates.map((x) => x.title),
        ),
        inverse: true,
        axisLabel: { color: t.textPrimary, fontSize: 13, fontWeight: 600 },
      },
      series: series.map((s) => ({
        type: 'bar' as const,
        name: s.name,
        data: s.rates,
        barMaxWidth: 16,
        barGap: '25%',
        barCategoryGap: '28%',
        itemStyle: { color: s.color, borderRadius: [0, RADIUS, RADIUS, 0] },
        label: {
          show: true,
          position: 'right' as const,
          formatter: (p: { dataIndex: number }) => {
            const gain = extra(s, p.dataIndex);
            return `{rate|${pct(s.rates[p.dataIndex])}}  {note|${describe(s, p.dataIndex)}}${gain ? `  {gain|${gain}}` : ''}`;
          },
          rich: {
            rate: { color: t.textPrimary, fontSize: 12, fontWeight: 700 },
            note: { color: t.textSecondary, fontSize: 12 },
            gain: { color: t.textPrimary, fontSize: 12, fontWeight: 700 },
          },
        },
      })),
    },
    table: {
      columns: ['Вид', ...series.flatMap((s) => [`${s.name}, % КВ`, `договоров ${s.source}`])],
      rows: r.rates.map((x, i) => [
        x.title,
        ...series.flatMap((s) => [pct(s.rates[i]), formatInteger(s.contracts[i])]),
      ]),
    },
  };
}

/** АВ income per quarter: the forecast plus what the plan adds on top. */
export function incomeChart(r: KvRecommendations, t: ChartTokens): ChartView {
  const quarters = [r.quarter, r.nextQuarter];
  const forecast = [r.income.current, r.income.next];
  const added = [r.planEffect?.salesEffect ?? 0, r.planEffect?.rateEffect ?? 0];
  return {
    option: {
      ...baseOption(t),
      grid: { left: 8, right: 16, top: 52, bottom: 8, containLabel: true },
      legend: legend(t),
      tooltip: {
        ...baseOption(t).tooltip,
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        valueFormatter: (v) => money(Number(v)),
      },
      xAxis: categoryAxis(t, quarters),
      yAxis: valueAxis(t, formatCompact),
      series: [
        {
          type: 'bar',
          name: 'Прогноз АВ',
          stack: 'income',
          data: forecast,
          barMaxWidth: 72,
          itemStyle: { color: t.series[0], borderColor: t.surface, borderWidth: 1 },
        },
        {
          type: 'bar',
          name: 'Прирост в максимальном варианте',
          stack: 'income',
          data: added,
          barMaxWidth: 72,
          itemStyle: {
            color: t.series[2],
            borderColor: t.surface,
            borderWidth: 1,
            borderRadius: [RADIUS, RADIUS, 0, 0],
          },
          label: {
            show: true,
            position: 'top',
            color: t.textPrimary,
            fontSize: 12,
            fontWeight: 600,
            formatter: (p) => formatCompact(forecast[p.dataIndex] + added[p.dataIndex]),
          },
        },
      ],
    },
    table: {
      columns: [
        'Квартал',
        'Прогноз АВ',
        'Прирост в максимальном варианте',
        'Итого в максимальном варианте',
      ],
      rows: quarters.map((q, i) => [
        q,
        money(forecast[i]),
        money(added[i]),
        money(forecast[i] + added[i]),
      ]),
    },
  };
}

/** What to sell this quarter: plan amount per priority line. */
export const salesPlanChart = (r: KvRecommendations, t: ChartTokens): ChartView =>
  horizontalBars(
    r.sell.rows
      .filter((row) => row.priority && row.planAmount > 0)
      .map((row) => ({ name: row.title, value: row.planAmount })),
    t,
    {
      format: formatCompact,
      tableFormat: money,
      valueLabel: 'План продаж',
      nameLabel: 'Вид',
      color: t.series[2],
    },
  );

/** Portfolio to prolong: contracts due by product. */
export const portfolioChart = (r: KvRecommendations, t: ChartTokens): ChartView =>
  horizontalBars(
    [...r.portfolio.groups]
      .sort((a, b) => b.count - a.count)
      .map((g) => ({ name: `${g.title} · ${g.product}`, value: g.count })),
    t,
    {
      format: formatInteger,
      tableFormat: formatInteger,
      valueLabel: 'Договоров',
      nameLabel: 'Продукт',
    },
  );
