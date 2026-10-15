import { ChartTokens } from '../../core/services/theme.service';
import { BonusForecast, BonusSummary, ModelScore, PlanRow } from '../../core/models/bonus.model';
import { ChartView } from '../../shared/components/chart-card/chart-card.component';
import {
  formatCompact,
  formatInteger,
  formatMoney,
  formatPercent,
} from '../../shared/utils/format';
import {
  BAR_MAX_WIDTH,
  baseOption,
  categoryAxis,
  horizontalBars,
  legend,
  RADIUS,
  valueAxis,
} from '../dashboard/chart-options/base';

export const RECOMMENDED_PLAN_LABEL = 'Рекомендуемый план на основе прогноза';

interface QuarterTotal {
  quarter: string;
  plan: number;
  fact: number;
}

/** Sums recommended plans and facts of completed quarters across the filtered agents. */
export function completedTotals(rows: PlanRow[]): QuarterTotal[] {
  const totals = rows
    .filter((row) => row.kind === 'completed')
    .reduce((acc, row) => {
      const current = acc.get(row.quarter) ?? { quarter: row.quarter, plan: 0, fact: 0 };
      return acc.set(row.quarter, {
        ...current,
        plan: current.plan + row.recommendedPlan,
        fact: current.fact + (row.fact ?? 0),
      });
    }, new Map<string, QuarterTotal>());
  return [...totals.values()].sort((a, b) => a.quarter.localeCompare(b.quarter));
}

/** Completed quarters only: fact as columns, recommended plan as a line — same unit, one axis. */
export function planFactChart(rows: PlanRow[], t: ChartTokens): ChartView {
  const totals = completedTotals(rows);
  return {
    option: {
      ...baseOption(t),
      grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
      legend: legend(t),
      tooltip: {
        ...baseOption(t).tooltip,
        trigger: 'axis',
        valueFormatter: (v) => formatInteger(Number(v)),
      },
      xAxis: categoryAxis(
        t,
        totals.map((q) => q.quarter),
      ),
      yAxis: valueAxis(t, formatCompact),
      series: [
        {
          type: 'bar',
          name: 'Фактические сборы',
          data: totals.map((q) => q.fact),
          barMaxWidth: BAR_MAX_WIDTH,
          itemStyle: { color: t.series[0], borderRadius: [RADIUS, RADIUS, 0, 0] },
        },
        {
          type: 'line',
          name: RECOMMENDED_PLAN_LABEL,
          data: totals.map((q) => q.plan),
          symbol: 'circle',
          symbolSize: 8,
          lineStyle: { width: 2, color: t.series[1] },
          itemStyle: { color: t.series[1], borderColor: t.surface, borderWidth: 2 },
        },
      ],
    },
    table: {
      columns: ['Квартал', 'Рекомендуемый план', 'Факт', 'Выполнение'],
      rows: totals.map((q) => [
        q.quarter,
        formatInteger(q.plan),
        formatInteger(q.fact),
        formatPercent((q.fact / q.plan) * 100),
      ]),
    },
  };
}

export const bonusByAgentChart = (items: BonusSummary[], t: ChartTokens): ChartView =>
  horizontalBars(
    items.map((i) => ({ name: i.agent, value: i.bonus })),
    t,
    { format: formatMoney, tableFormat: formatMoney, valueLabel: 'Премия', nameLabel: 'Агент' },
  );

export const modelQualityChart = (scores: ModelScore[], t: ChartTokens): ChartView =>
  horizontalBars(
    scores.map((s) => ({ name: s.title, value: s.wape * 100 })),
    t,
    {
      format: formatPercent,
      tableFormat: formatPercent,
      valueLabel: 'Ошибка WAPE (синтетический набор)',
      nameLabel: 'Модель',
    },
  );

/** Employee bonus outlook: bonus vs. next-quarter collections, model forecast and rule kinks marked. */
export function bonusForecastChart(f: BonusForecast, t: ChartTokens): ChartView {
  const refundLimit = formatPercent(f.config.max_refund_share * 100);
  const marks = [
    { xAxis: f.threshold, name: 'Порог плана', color: t.muted },
    ...(f.capReachedAt === null
      ? []
      : [{ xAxis: f.capReachedAt, name: 'Потолок премии', color: t.muted }]),
  ];
  return {
    option: {
      ...baseOption(t),
      grid: { left: 8, right: 24, top: 56, bottom: 28, containLabel: true },
      legend: legend(t),
      tooltip: {
        ...baseOption(t).tooltip,
        trigger: 'axis',
        formatter: (params) => {
          const items = Array.isArray(params) ? params : [params];
          const fact = Number((items[0].value as number[])[0]);
          const lines = items.map(
            (p) =>
              `${p.marker}${p.seriesName}: <b>${formatInteger(Number((p.value as number[])[1]))}</b>`,
          );
          return [
            `Сборы ${formatInteger(fact)} (${formatPercent((fact / f.forecastCollections) * 100)} плана)`,
            ...lines,
          ].join('<br/>');
        },
      },
      xAxis: {
        ...valueAxis(t, formatCompact),
        min: 'dataMin',
        name: `Сборы за ${f.quarter}`,
        nameLocation: 'middle',
        nameGap: 28,
        nameTextStyle: { color: t.muted },
      },
      yAxis: valueAxis(t, formatCompact),
      series: [
        {
          type: 'line',
          name: `Премия при возвратах ≤ ${refundLimit}`,
          data: f.curve.map((p) => [p.fact, p.bonus]),
          showSymbol: false,
          lineStyle: { width: 2, color: t.series[0] },
          itemStyle: { color: t.series[0] },
          markLine: {
            silent: true,
            symbol: 'none',
            data: marks.map((m) => ({
              xAxis: m.xAxis,
              lineStyle: { color: m.color, type: 'dashed', width: 1 },
              label: { formatter: m.name, color: t.textSecondary, fontSize: 11 },
            })),
          },
        },
        {
          type: 'line',
          name: `Премия при возвратах > ${refundLimit}`,
          data: f.curve.map((p) => [p.fact, p.bonus_high_refunds]),
          showSymbol: false,
          lineStyle: { width: 2, type: 'dashed', color: t.series[1] },
          itemStyle: { color: t.series[1] },
        },
        {
          type: 'scatter',
          name: 'Прогноз сборов модели',
          data: [[f.forecastCollections, f.forecastBonus]],
          symbolSize: 12,
          itemStyle: { color: t.series[2], borderColor: t.surface, borderWidth: 2 },
          label: {
            show: true,
            position: 'top',
            color: t.textPrimary,
            fontSize: 12,
            formatter: `прогноз: премия ${formatInteger(f.forecastBonus)}`,
          },
          z: 3,
        },
      ],
    },
    table: {
      columns: [
        'Сборы',
        '% плана',
        `Премия (возвраты ≤ ${refundLimit})`,
        `Премия (возвраты > ${refundLimit})`,
      ],
      rows: f.curve.map((p) => [
        formatInteger(p.fact),
        formatPercent((p.fact / f.forecastCollections) * 100),
        formatInteger(p.bonus),
        formatInteger(p.bonus_high_refunds),
      ]),
    },
  };
}
