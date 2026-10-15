import { ChartTokens } from '../../core/services/theme.service';
import { KvRecommendations } from '../../core/models/kv.model';
import { ChartView } from '../../shared/components/chart-card/chart-card.component';
import { formatCompact, formatInteger } from '../../shared/utils/format';
import {
  RADIUS,
  baseOption,
  categoryAxis,
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

/** Where the rates axis starts: 5 п.п. below the lowest forecast, so the gain on top gets visible length. */
export function ratesAxisMin(r: KvRecommendations): number {
  const lowest = Math.min(...r.rates.map((x) => x.next ?? 0));
  return Math.max(0, Math.floor((lowest - 0.05) * 20) / 20);
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
      yAxis: { ...valueAxis(t, (v) => pct(v)), min: ratesAxisMin(r) },
      series: [
        {
          type: 'bar',
          name: `Прогноз ${r.nextQuarter}`,
          stack: 'rate',
          data: forecast,
          barMaxWidth: 48,
          itemStyle: { color: t.series[0], borderColor: t.surface, borderWidth: 1 },
          label: {
            show: true,
            position: 'insideTop',
            color: '#ffffff',
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
            color: t.sequential[1],
            borderColor: t.surface,
            borderWidth: 1,
            borderRadius: [RADIUS, RADIUS, 0, 0],
          },
          label: {
            show: true,
            position: 'top',
            color: t.textPrimary,
            fontSize: 13,
            fontWeight: 700,
            formatter: (p) => pct(target[p.dataIndex]),
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
