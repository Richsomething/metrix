import { ChangeDetectionStrategy, Component, computed, inject, linkedSignal, output } from '@angular/core';
import { dataOf, errorMessage } from '../../core/services/bonus-api.service';
import { KvApiService } from '../../core/services/kv-api.service';
import { KvRecommendations, KvSellRow } from '../../core/models/kv.model';
import { formatInteger } from '../../shared/utils/format';

const pctFormat = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 });
const BONUSES: { key: 'd1' | 'd2' | 'd3'; title: string; why: string }[] = [
  { key: 'd1', title: 'Доп.АВ1', why: 'рост продаж' },
  { key: 'd2', title: 'Доп.АВ2', why: 'доля некаско-продуктов' },
  { key: 'd3', title: 'Доп.АВ3', why: 'продление портфеля' },
];
const dateFormat = new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit' });

/** Main page: АВ rates by line and what to do this quarter — prolong the portfolio, sell priority lines. */
@Component({
  selector: 'app-home',
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HomeComponent {
  /** Asks the shell to open the detailed АВ tab. */
  readonly openDetails = output<void>();

  private readonly api = inject(KvApiService);
  private readonly optionsRef = this.api.options();
  protected readonly options = computed(() => dataOf(this.optionsRef));
  protected readonly agent = linkedSignal(() => this.options()?.agents[0] ?? '');

  private readonly recRef = this.api.recommendations(this.agent);
  protected readonly rec = computed(() => dataOf(this.recRef));
  protected readonly error = computed(() => {
    const e = this.optionsRef.error() ?? this.recRef.error();
    return e ? errorMessage(e) : '';
  });

  /** «Доп.АВ1 +1 п.п. (рост продаж), Доп.АВ3 +2 п.п. (продление КАСКО)» — only the bonuses the plan adds. */
  protected readonly planBonuses = computed(() => {
    const c = this.rec()?.planComponents;
    if (!c?.after) return '';
    return BONUSES.filter((b) => (c.after![b.key] ?? 0) - (c.before[b.key] ?? 0) > 1e-9)
      .map((b) => `${b.title} +${pctFormat.format(((c.after![b.key] ?? 0) - (c.before[b.key] ?? 0)) * 100)} п.п. (${b.why})`)
      .join(', ');
  });

  protected readonly priorityRows = computed(() => this.rec()?.sell.rows.filter((r) => r.priority) ?? []);
  protected readonly kaskoRow = computed(() => this.rec()?.sell.rows.find((r) => !r.priority) ?? null);
  protected readonly planNeeded = computed(() => (this.rec()?.sell.total ?? 0) > 0);

  protected money(value: number | null | undefined): string {
    return value === null || value === undefined ? '—' : `${formatInteger(value)} ₽`;
  }

  protected pct(value: number | null | undefined): string {
    return value === null || value === undefined ? '—' : `${pctFormat.format(value * 100)}%`;
  }


  /** Percentage points: 0.05 → «+5 п.п.». */
  protected points(value: number | null): string {
    return value === null ? '—' : `+${pctFormat.format(value * 100)} п.п.`;
  }

  /** Target minus forecast in percentage points: 0.28 → 0.30 gives «+2 п.п.». */
  protected gap(forecast: number | null, target: number | null): string {
    return forecast === null || target === null ? '—' : this.points(Math.max(0, target - forecast));
  }

  protected date(iso: string): string {
    return dateFormat.format(new Date(iso));
  }

  protected maxGain(r: KvRecommendations): string {
    const values = Object.values(r.portfolio.gain);
    return values.length ? `+${pctFormat.format(Math.max(...values) * 100)} п.п.` : '0';
  }

  protected products(row: KvSellRow): string {
    return row.products.map((p) => p.product).join(', ') || '—';
  }

  protected textValue(event: Event): string {
    return (event.target as HTMLSelectElement).value;
  }
}
