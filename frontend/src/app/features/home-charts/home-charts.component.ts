import { ChangeDetectionStrategy, Component, computed, inject, linkedSignal } from '@angular/core';
import { dataOf, errorMessage } from '../../core/services/bonus-api.service';
import { KvApiService } from '../../core/services/kv-api.service';
import { ThemeService } from '../../core/services/theme.service';
import { ChartCardComponent } from '../../shared/components/chart-card/chart-card.component';
import { formatCompact } from '../../shared/utils/format';
import {
  collectionsChart,
  portfolioChart,
  ratesAxisMin,
  ratesChart,
  salesPlanChart,
} from './home.charts';

const ROW_HEIGHT_PX = 34;
const MIN_BAR_CHART_PX = 220;
const barsHeight = (rows: number): string =>
  `${Math.max(MIN_BAR_CHART_PX, rows * ROW_HEIGHT_PX + 40)}px`;

/** The main page's numbers as charts: rates, income, sales plan and portfolio to prolong. */
@Component({
  selector: 'app-home-charts',
  imports: [ChartCardComponent],
  templateUrl: './home-charts.component.html',
  styleUrl: './home-charts.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HomeChartsComponent {
  private readonly api = inject(KvApiService);
  private readonly tokens = inject(ThemeService).tokens;

  private readonly optionsRef = this.api.options();
  protected readonly options = computed(() => dataOf(this.optionsRef));
  protected readonly agent = linkedSignal(() => this.options()?.agents[0] ?? '');

  private readonly recRef = this.api.recommendations(this.agent);
  protected readonly rec = computed(() => dataOf(this.recRef));
  protected readonly error = computed(() => {
    const e = this.optionsRef.error() ?? this.recRef.error();
    return e ? errorMessage(e) : '';
  });

  protected readonly charts = computed(() => {
    const r = this.rec();
    const t = this.tokens();
    if (!r) return null;
    const sales = salesPlanChart(r, t);
    const portfolio = portfolioChart(r, t);
    return {
      rates: ratesChart(r, t),
      ratesAxisFrom: Math.round(ratesAxisMin(r) * 100),
      collections: collectionsChart(r, t),
      collectionsTotal: formatCompact(
        Math.max(r.income.currentBase, r.income.currentCollected) + r.sell.total,
      ),
      sales,
      salesHeight: barsHeight(sales.table.rows.length),
      portfolio,
      portfolioHeight: barsHeight(portfolio.table.rows.length),
    };
  });

  protected textValue(event: Event): string {
    return (event.target as HTMLSelectElement).value;
  }
}
