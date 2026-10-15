import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  effect,
  ElementRef,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';
import * as echarts from 'echarts/core';
import { BarChart, HeatmapChart, LineChart, ScatterChart } from 'echarts/charts';
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsOption } from 'echarts';

echarts.use([
  BarChart,
  LineChart,
  HeatmapChart,
  ScatterChart,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

/** Thin ECharts wrapper: creates the instance after render, resizes with its box, re-applies options on change. */
@Component({
  selector: 'app-chart',
  template: `<div #host class="chart" role="img" [attr.aria-label]="label()"></div>`,
  styles: `
    :host {
      display: block;
    }
    .chart {
      width: 100%;
      height: var(--chart-height, 300px);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ChartComponent {
  readonly option = input.required<EChartsOption>();
  readonly label = input('');

  private readonly host = viewChild.required<ElementRef<HTMLDivElement>>('host');
  private readonly instance = signal<echarts.ECharts | null>(null);

  constructor() {
    const destroyRef = inject(DestroyRef);

    afterNextRender(() => {
      const element = this.host().nativeElement;
      const chart = echarts.init(element);
      const observer = new ResizeObserver(() => chart.resize());
      observer.observe(element);
      this.instance.set(chart);

      destroyRef.onDestroy(() => {
        observer.disconnect();
        chart.dispose();
      });
    });

    effect(() => {
      this.instance()?.setOption(this.option(), { notMerge: true });
    });
  }
}
