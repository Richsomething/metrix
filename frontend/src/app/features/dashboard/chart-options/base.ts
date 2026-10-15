import type { EChartsOption, XAXisComponentOption, YAXisComponentOption } from 'echarts';
import { ChartTokens } from '../../../core/services/theme.service';
import { NamedValue } from '../../../core/models/dashboard.model';
import { ChartView } from '../../../shared/components/chart-card/chart-card.component';

export type Formatter = (value: number) => string;

export interface ItemParams {
  dataIndex: number;
  value: unknown;
}

/** Item-trigger tooltips get one params object; axis triggers get an array — normalize to the first item. */
export function itemParams(params: unknown): ItemParams {
  const first = Array.isArray(params) ? params[0] : params;
  return first as ItemParams;
}

const FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif';
export const BAR_MAX_WIDTH = 28;
export const RADIUS = 4;

/** Shared chrome: recessive axes, hairline grid, surface-colored tooltip. */
export function baseOption(t: ChartTokens): EChartsOption {
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: FONT, color: t.textSecondary },
    grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
    tooltip: {
      backgroundColor: t.surface,
      borderColor: t.border,
      textStyle: { color: t.textPrimary, fontSize: 13 },
      extraCssText: 'border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,0.12);',
    },
  };
}

export function categoryAxis(
  t: ChartTokens,
  data: string[],
): XAXisComponentOption & YAXisComponentOption {
  return {
    type: 'category',
    data,
    axisLine: { lineStyle: { color: t.axis } },
    axisTick: { show: false },
    axisLabel: { color: t.muted, fontSize: 12 },
  };
}

export function valueAxis(
  t: ChartTokens,
  format: Formatter,
): XAXisComponentOption & YAXisComponentOption {
  return {
    type: 'value',
    axisLine: { show: false },
    axisLabel: { color: t.muted, fontSize: 12, formatter: (v: number) => format(v) },
    splitLine: { lineStyle: { color: t.grid } },
  };
}

export function legend(t: ChartTokens): EChartsOption['legend'] {
  return {
    top: 0,
    left: 0,
    icon: 'roundRect',
    itemWidth: 10,
    itemHeight: 10,
    textStyle: { color: t.textSecondary, fontSize: 12 },
  };
}

export interface BarOptions {
  format: Formatter;
  tableFormat: Formatter;
  valueLabel: string;
  nameLabel: string;
  color?: string;
}

/** Ranked horizontal bars, largest on top, 4px rounded data-end. */
export function horizontalBars(items: NamedValue[], t: ChartTokens, o: BarOptions): ChartView {
  return {
    option: {
      ...baseOption(t),
      // Bars carry direct value labels, so the value scale is hidden; the right gutter fits the widest label.
      grid: { left: 8, right: 72, top: 4, bottom: 4, containLabel: true },
      tooltip: {
        ...baseOption(t).tooltip,
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        valueFormatter: (v) => o.tableFormat(Number(v)),
      },
      xAxis: { ...valueAxis(t, o.format), axisLabel: { show: false } },
      yAxis: {
        ...categoryAxis(
          t,
          items.map((i) => i.name),
        ),
        inverse: true,
        axisLabel: { color: t.textSecondary, fontSize: 12, width: 180, overflow: 'truncate' },
      },
      series: [
        {
          type: 'bar',
          name: o.valueLabel,
          data: items.map((i) => i.value),
          barMaxWidth: BAR_MAX_WIDTH,
          itemStyle: { color: o.color ?? t.series[0], borderRadius: [0, RADIUS, RADIUS, 0] },
          label: {
            show: true,
            position: 'right',
            color: t.textSecondary,
            fontSize: 12,
            formatter: (p) => o.format(Number(p.value)),
          },
        },
      ],
    },
    table: {
      columns: [o.nameLabel, o.valueLabel],
      rows: items.map((i) => [i.name, o.tableFormat(i.value)]),
    },
  };
}

/** Single-series columns over time; only the latest bar is direct-labeled. */
export function timeColumns(items: NamedValue[], t: ChartTokens, o: BarOptions): ChartView {
  const last = items.length - 1;
  return {
    option: {
      ...baseOption(t),
      grid: { left: 8, right: 16, top: 28, bottom: 8, containLabel: true },
      tooltip: {
        ...baseOption(t).tooltip,
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        valueFormatter: (v) => o.tableFormat(Number(v)),
      },
      xAxis: categoryAxis(
        t,
        items.map((i) => i.name),
      ),
      yAxis: valueAxis(t, o.format),
      series: [
        {
          type: 'bar',
          name: o.valueLabel,
          data: items.map((i, index) => ({
            value: i.value,
            label: {
              show: index === last,
              position: 'top',
              color: t.textPrimary,
              fontSize: 12,
              fontWeight: 600,
              formatter: () => o.format(i.value),
            },
          })),
          barMaxWidth: BAR_MAX_WIDTH,
          itemStyle: { color: o.color ?? t.series[0], borderRadius: [RADIUS, RADIUS, 0, 0] },
        },
      ],
    },
    table: {
      columns: [o.nameLabel, o.valueLabel],
      rows: items.map((i) => [i.name, o.tableFormat(i.value)]),
    },
  };
}
