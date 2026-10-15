import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  linkedSignal,
  signal,
} from '@angular/core';
import { dataOf, errorMessage } from '../../core/services/bonus-api.service';
import { KvApiService } from '../../core/services/kv-api.service';
import { ThemeService } from '../../core/services/theme.service';
import { ChartCardComponent } from '../../shared/components/chart-card/chart-card.component';
import { formatCompact } from '../../shared/utils/format';
import { ratesAxisMin, ratesChart } from './home.charts';

/** Orange ramp for the lines inside «надо продать ещё», biggest first. */
const EXTRA_SHADES = ['#eb6834', '#f08a5d', '#f4ab87', '#f8ccb4', '#fbe0d1'];

/** The main page's numbers as charts: rates and this quarter's collections with the sales plan. */
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
    return {
      rates: ratesChart(r, t),
      ratesAxisFrom: Math.round(ratesAxisMin(r) * 100),
    };
  });

  /** This quarter's collections: collected so far, the forecast for the rest, the extra for the maximum rate. */
  protected readonly collections = computed(() => {
    const r = this.rec();
    if (!r) return null;
    const collected = r.income.currentCollected;
    const rest = Math.max(0, r.income.currentBase - collected);
    const extra = r.sell.total;
    const total = collected + rest + extra;
    const share = (v: number): number => (total > 0 ? (v / total) * 100 : 0);
    // the orange part is split by the priority lines of the sales plan, biggest first
    const lines = r.sell.rows
      .filter((row) => row.priority && row.planAmount > 0)
      .sort((a, b) => b.planAmount - a.planAmount);
    const largest = lines[0]?.planAmount ?? 0;
    return {
      collected: this.money(collected),
      rest: this.money(rest),
      extra: this.money(extra),
      total: this.money(total),
      collectedPct: share(collected),
      restPct: share(rest),
      extraPct: share(extra),
      lines: lines.map((row, i) => ({
        title: row.title,
        amount: this.money(row.planAmount),
        contracts: row.planContracts,
        share: row.planAmount,
        relative: largest > 0 ? (row.planAmount / largest) * 100 : 0,
        shade: EXTRA_SHADES[Math.min(i, EXTRA_SHADES.length - 1)],
      })),
    };
  });

  /** The popup with the sales plan by line is open while the orange part is hovered, focused or tapped. */
  protected readonly extraOpen = signal(false);
  /** The line under the cursor, highlighted in the popup; −1 for none. */
  protected readonly activeLine = signal(-1);

  protected money(value: number): string {
    return `${formatCompact(value)} ₽`;
  }

  protected textValue(event: Event): string {
    return (event.target as HTMLSelectElement).value;
  }
}
