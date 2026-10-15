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
 * Next quarter's АВ rate by line: the forecast as the column, the gain in the maximum option stacked on top.
 * Contract counts behind both live in the tooltip and the table, not on the chart.
 */
export function ratesChart(r: KvRecommendations, t: ChartTokens): ChartView {
  const forecast = r.rates.map((x) => x.next ?? 0);
  const target = r.rates.map((x) => x.nextWithPlan ?? x.next ?? 0);
  const gain = target.map((v, i) => Math.max(0, v - forecast[i]));
  const points = (v: number): string => `+${pctFormat.format(v * 100)} п.п.`;
  const contracts = (n: number): string =>
    `≈ ${formatInteger(n)} ${contractsWord(n)} за ${r.quarter}`;
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
          const i = (params as { dataIndex: number }[])[0].dataIndex;
          const x = r.rates[i];
          return [
            `<b>${x.title}</b>`,
            `Прогноз ${r.nextQuarter}: <b>${pct(forecast[i])}</b> · ${contracts(x.contracts.next)}`,
            `Цель: <b>${pct(target[i])}</b> · ${contracts(x.contracts.nextWithPlan)}`,
            `Прирост: <b>${points(gain[i])}</b>${x.cappedWithPlan ? ' · выше нельзя' : ''}`,
          ].join('<br>');
        },
      },
      xAxis: {
        ...categoryAxis(
          t,
          r.rates.map((x) => x.title),
        ),
        axisLabel: { color: t.textPrimary, fontSize: 13, fontWeight: 600 },
      },
      yAxis: valueAxis(t, (v) => pct(v)),
      series: [
        {
          type: 'bar',
          name: `Прогноз ${r.nextQuarter}`,
          stack: 'rate',
          data: forecast,
          barMaxWidth: 48,
          itemStyle: { color: t.sequential[1], borderColor: t.surface, borderWidth: 1 },
          label: {
            show: true,
            position: 'insideTop',
            color: t.textPrimary,
            fontSize: 12,
            fontWeight: 600,
            formatter: (p) => pct(forecast[p.dataIndex]),
          },
        },
        {
          type: 'bar',
          name: 'Прирост в максимальном варианте',
          stack: 'rate',
          data: gain,
          barMaxWidth: 48,
          itemStyle: {
            color: t.series[0],
            borderColor: t.surface,
            borderWidth: 1,
            borderRadius: [RADIUS, RADIUS, 0, 0],
          },
          label: {
            show: true,
            position: 'top',
            formatter: (p) =>
              `{gain|${points(gain[p.dataIndex])}}  {total|${pct(target[p.dataIndex])}}`,
            rich: {
              gain: { color: t.series[0], fontSize: 13, fontWeight: 700 },
              total: { color: t.textPrimary, fontSize: 13, fontWeight: 700 },
            },
          },
        },
      ],
    },
    table: {
      columns: [
        'Вид',
        `Прогноз ${r.nextQuarter}`,
        'Цель',
        'Прирост',
        `Договоров (прогноз)`,
        `Договоров (цель)`,
      ],
      rows: r.rates.map((x, i) => [
        x.title,
        pct(forecast[i]),
        pct(target[i]),
        points(gain[i]),
        formatInteger(x.contracts.next),
        formatInteger(x.contracts.nextWithPlan),
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
