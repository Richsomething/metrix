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

/** АВ rates by line: base → this quarter → next quarter forecast → next quarter if the plan is met. */
export function ratesChart(r: KvRecommendations, t: ChartTokens): ChartView {
  const series = [
    { name: 'База', values: r.rates.map((x) => x.base) },
    { name: r.quarter, values: r.rates.map((x) => x.current) },
    { name: `${r.nextQuarter} прогноз`, values: r.rates.map((x) => x.next) },
    { name: `${r.nextQuarter} с планом`, values: r.rates.map((x) => x.nextWithPlan) },
  ];
  return {
    option: {
      ...baseOption(t),
      grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
      legend: legend(t),
      tooltip: {
        ...baseOption(t).tooltip,
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        valueFormatter: (v) => pct(v === null || v === undefined ? null : Number(v)),
      },
      xAxis: categoryAxis(
        t,
        r.rates.map((x) => x.title),
      ),
      yAxis: valueAxis(t, (v) => pct(v)),
      series: series.map((s, index) => ({
        type: 'bar' as const,
        name: s.name,
        data: s.values,
        barMaxWidth: 18,
        barGap: '15%',
        itemStyle: { color: t.series[index], borderRadius: [RADIUS, RADIUS, 0, 0] },
        // Only the target series is direct-labeled; the rest is in the legend, tooltip and table.
        label: {
          show: index === series.length - 1,
          position: 'top' as const,
          color: t.textPrimary,
          fontSize: 11,
          fontWeight: 600,
          formatter: (p: { value: unknown }) => pct(p.value === null ? null : Number(p.value)),
        },
      })),
    },
    table: {
      columns: ['Вид', ...series.map((s) => s.name)],
      rows: r.rates.map((x, i) => [x.title, ...series.map((s) => pct(s.values[i]))]),
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
          name: 'Прирост с планом',
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
      columns: ['Квартал', 'Прогноз АВ', 'Прирост с планом', 'Итого с планом'],
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
