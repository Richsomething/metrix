import type { BarSeriesOption } from 'echarts';
import { ChartTokens } from '../../../core/services/theme.service';
import {
  AgentTenure,
  Heatmap,
  NamedValue,
  SeriesMatrix,
} from '../../../core/models/dashboard.model';
import { ChartView } from '../../../shared/components/chart-card/chart-card.component';
import { formatCompact, formatInteger, formatYears } from '../../../shared/utils/format';
import {
  baseOption,
  BAR_MAX_WIDTH,
  categoryAxis,
  horizontalBars,
  itemParams,
  legend,
  RADIUS,
  timeColumns,
  valueAxis,
} from './base';

const MONEY = { format: formatCompact, tableFormat: formatInteger, valueLabel: 'Сборы' };

export const quarterlyChart = (items: NamedValue[], t: ChartTokens): ChartView =>
  timeColumns(items, t, { ...MONEY, nameLabel: 'Квартал' });

export const agentsChart = (items: NamedValue[], t: ChartTokens): ChartView =>
  horizontalBars(items, t, { ...MONEY, nameLabel: 'Агент' });

export const branchesChart = (items: NamedValue[], t: ChartTokens): ChartView =>
  horizontalBars(items, t, { ...MONEY, nameLabel: 'Филиал' });

export const groupsChart = (items: NamedValue[], t: ChartTokens): ChartView =>
  horizontalBars(items, t, { ...MONEY, nameLabel: 'Группа' });

export const productsChart = (items: NamedValue[], t: ChartTokens): ChartView =>
  horizontalBars(items, t, { ...MONEY, nameLabel: 'Продукт' });

/** Stacked columns per quarter; a 1px surface border gives the 2px gap between segments. */
export function linesChart(matrix: SeriesMatrix, t: ChartTokens): ChartView {
  const topIndex = matrix.series.length - 1;
  const series: BarSeriesOption[] = matrix.series.map((s, index) => ({
    type: 'bar',
    name: s.name,
    stack: 'total',
    data: s.values,
    barMaxWidth: BAR_MAX_WIDTH,
    emphasis: { focus: 'series' },
    itemStyle: {
      color: t.series[index],
      borderColor: t.surface,
      borderWidth: 1,
      borderRadius: index === topIndex ? [RADIUS, RADIUS, 0, 0] : 0,
    },
  }));

  return {
    option: {
      ...baseOption(t),
      grid: { left: 8, right: 16, top: 56, bottom: 8, containLabel: true },
      legend: legend(t),
      tooltip: {
        ...baseOption(t).tooltip,
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        valueFormatter: (v) => formatInteger(Number(v)),
      },
      xAxis: categoryAxis(t, matrix.quarters),
      yAxis: valueAxis(t, formatCompact),
      series,
    },
    table: {
      columns: ['Квартал', ...matrix.series.map((s) => s.name)],
      rows: matrix.quarters.map((q, qi) => [
        q,
        ...matrix.series.map((s) => formatInteger(s.values[qi])),
      ]),
    },
  };
}

export function agentHeatmapChart(heatmap: Heatmap, t: ChartTokens): ChartView {
  const values = heatmap.values.map(([, , v]) => v);
  return {
    option: {
      ...baseOption(t),
      grid: { left: 8, right: 16, top: 8, bottom: 56, containLabel: true },
      tooltip: {
        ...baseOption(t).tooltip,
        formatter: (p) => {
          const [qi, ai, v] = itemParams(p).value as [number, number, number];
          return `${heatmap.agents[ai]}<br/>${heatmap.quarters[qi]}: <b>${formatInteger(v)}</b>`;
        },
      },
      xAxis: { ...categoryAxis(t, heatmap.quarters), splitArea: { show: false } },
      yAxis: {
        ...categoryAxis(t, heatmap.agents),
        axisLabel: { color: t.textSecondary, fontSize: 12 },
      },
      visualMap: {
        min: Math.min(0, ...values),
        max: Math.max(1, ...values),
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
        itemHeight: 240,
        itemWidth: 10,
        calculable: false,
        text: ['больше', 'меньше'],
        textStyle: { color: t.muted, fontSize: 12 },
        inRange: { color: [...t.sequential] },
      },
      series: [
        {
          type: 'heatmap',
          data: heatmap.values,
          itemStyle: { borderColor: t.surface, borderWidth: 2, borderRadius: RADIUS },
          emphasis: { itemStyle: { borderColor: t.textPrimary, borderWidth: 1 } },
        },
      ],
    },
    table: {
      columns: ['Агент', ...heatmap.quarters],
      rows: heatmap.agents.map((agent, ai) => [
        agent,
        ...heatmap.quarters.map((_, qi) =>
          formatInteger(heatmap.values[ai * heatmap.quarters.length + qi][2]),
        ),
      ]),
    },
  };
}

export function tenureChart(items: AgentTenure[], t: ChartTokens): ChartView {
  return {
    option: {
      ...baseOption(t),
      grid: { left: 8, right: 32, top: 24, bottom: 24, containLabel: true },
      tooltip: {
        ...baseOption(t).tooltip,
        formatter: (p) => {
          const item = items[itemParams(p).dataIndex];
          return `${item.name}<br/>Стаж: <b>${formatYears(item.years)}</b><br/>Сборы: <b>${formatInteger(item.value)}</b>`;
        },
      },
      xAxis: {
        ...valueAxis(t, formatYears),
        name: 'Стаж с 1-го АД',
        nameLocation: 'middle',
        nameGap: 28,
        nameTextStyle: { color: t.muted },
      },
      yAxis: valueAxis(t, formatCompact),
      series: [
        {
          type: 'scatter',
          data: items.map((i) => [i.years, i.value]),
          symbolSize: 12,
          itemStyle: { color: t.series[0], borderColor: t.surface, borderWidth: 2 },
          label: {
            show: true,
            position: 'right',
            color: t.textSecondary,
            fontSize: 11,
            formatter: (p) => items[p.dataIndex].name.split(' ')[0],
          },
          labelLayout: { hideOverlap: true },
        },
      ],
    },
    table: {
      columns: ['Агент', 'Стаж', 'Сборы'],
      rows: items.map((i) => [i.name, formatYears(i.years), formatInteger(i.value)]),
    },
  };
}
