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

/**
 * АВ rates by line: this quarter → next quarter forecast → next quarter if the plan is met.
 * Each bar is labeled with the contracts behind its rate (quarter T's rate comes from the sales of T−1).
 */
export function ratesChart(r: KvRecommendations, t: ChartTokens): ChartView {
  const series = [
    {
      name: r.quarter,
      color: t.series[1],
      rates: r.rates.map((x) => x.current),
      contracts: r.rates.map((x) => x.contracts.current),
    },
    {
      name: `${r.nextQuarter} прогноз`,
      color: t.series[2],
      rates: r.rates.map((x) => x.next),
      contracts: r.rates.map((x) => x.contracts.next),
    },
    {
      name: `${r.nextQuarter} цель (максимальный вариант)`,
      color: t.series[3],
      rates: r.rates.map((x) => x.nextWithPlan),
      contracts: r.rates.map((x) => x.contracts.nextWithPlan),
    },
  ];
  return {
    option: {
      ...baseOption(t),
      grid: { left: 8, right: 16, top: 44, bottom: 8, containLabel: true },
      legend: legend(t),
      tooltip: {
        ...baseOption(t).tooltip,
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: unknown) => {
          const items = params as { dataIndex: number; seriesIndex: number; marker: string }[];
          const i = items[0].dataIndex;
          const lines = items.map((p) => {
            const s = series[p.seriesIndex];
            const n = s.contracts[i];
            return `${p.marker}${s.name}: <b>${pct(s.rates[i])}</b> · ${formatInteger(n)} ${contractsWord(n)}`;
          });
          return [`<b>${r.rates[i].title}</b>`, ...lines].join('<br>');
        },
      },
      xAxis: categoryAxis(
        t,
        r.rates.map((x) => x.title),
      ),
      yAxis: {
        ...valueAxis(t, (v) => pct(v)),
        name: '% КВ',
        nameTextStyle: { color: t.muted, fontSize: 12 },
      },
      series: series.map((s) => ({
        type: 'bar' as const,
        name: s.name,
        data: s.rates,
        barMaxWidth: 22,
        barGap: '15%',
        itemStyle: { color: s.color, borderRadius: [RADIUS, RADIUS, 0, 0] },
        label: {
          show: true,
          position: 'top' as const,
          color: t.textPrimary,
          fontSize: 11,
          fontWeight: 600,
          formatter: (p: { dataIndex: number }) => formatInteger(s.contracts[p.dataIndex]),
        },
      })),
    },
    table: {
      columns: ['Вид', ...series.flatMap((s) => [`${s.name}, % КВ`, `${s.name}, договоров`])],
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
