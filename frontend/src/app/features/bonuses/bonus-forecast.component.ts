import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  linkedSignal,
} from '@angular/core';
import { BonusApiService, dataOf, errorMessage } from '../../core/services/bonus-api.service';
import { ThemeService } from '../../core/services/theme.service';
import { ChartCardComponent } from '../../shared/components/chart-card/chart-card.component';
import { formatInteger } from '../../shared/utils/format';
import { bonusForecastChart } from './bonus-charts';

/** The main view: one chart with the selected employee's bonus outlook for the next quarter. */
@Component({
  selector: 'app-bonus-forecast',
  imports: [ChartCardComponent],
  template: `
    @if (!agent()) {
    <div class="controls">
      <label class="field">
        <span>Работник</span>
        <select [value]="selected()" (change)="selected.set(valueOf($event))">
          @for (name of agents(); track name) {
            <option [value]="name" [selected]="name === selected()">{{ name }}</option>
          }
        </select>
      </label>
    </div>
    }

    @if (error()) {
      <p class="error" role="alert">{{ error() }}</p>
    } @else if (forecast(); as f) {
      <p class="summary">
        Прогноз сборов модели на {{ f.quarter }} —
        <strong>{{ formatInteger(f.forecastCollections) }}</strong
        >; это и есть рекомендуемый план, поэтому премия по прогнозу —
        <strong>{{ formatInteger(f.forecastBonus) }}</strong
        >. Премия появляется при сборах выше {{ formatInteger(f.threshold)
        }}{{
          f.capReachedAt === null
            ? '.'
            : ' и достигает потолка ' +
              formatInteger(f.config.cap_per_quarter) +
              ' при ' +
              formatInteger(f.capReachedAt) +
              '.'
        }}
      </p>
      <app-chart-card
        [title]="'Прогноз премии: ' + f.agent + ', ' + f.quarter"
        subtitle="Сколько премии получит работник при разных сборах за квартал (правила из bonus.json)"
        [view]="view()!"
        height="380px"
      />
      <p class="note">{{ f.note }}</p>
    } @else {
      <p class="status" role="status">Загружаю прогноз…</p>
    }
  `,
  styles: `
    :host {
      display: block;
    }
    .controls {
      margin-bottom: 12px;
    }
    .field {
      display: inline-flex;
      flex-direction: column;
      gap: 4px;
      min-width: 220px;
      font-size: 12px;
      color: var(--text-secondary);
    }
    select {
      height: 34px;
      padding: 0 10px;
      font: inherit;
      font-size: 13px;
      color: var(--text-primary);
      background: var(--surface-1);
      border: 1px solid var(--border-strong);
      border-radius: 8px;
    }
    select:focus-visible {
      outline: 2px solid var(--focus);
      outline-offset: 2px;
    }
    .summary,
    .note,
    .status {
      margin: 0 0 12px;
      font-size: 13px;
      line-height: 1.5;
      color: var(--text-secondary);
    }
    .summary strong {
      color: var(--text-primary);
    }
    .note {
      margin-top: 12px;
    }
    .error {
      padding: 12px 16px;
      border: 1px solid var(--critical);
      border-radius: 8px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BonusForecastComponent {
  readonly agents = input.required<string[]>();
  readonly defaultAgent = input('');
  /** Set by a parent that owns the agent choice: the selector is hidden. */
  readonly agent = input('');

  private readonly api = inject(BonusApiService);
  private readonly tokens = inject(ThemeService).tokens;

  protected readonly selected = linkedSignal(
    () => this.agent() || this.defaultAgent() || this.agents()[0] || '',
  );
  private readonly resource = this.api.bonusForecast(this.selected);

  protected readonly forecast = computed(() => dataOf(this.resource));
  protected readonly view = computed(() => {
    const f = this.forecast();
    return f ? bonusForecastChart(f, this.tokens()) : null;
  });
  protected readonly error = computed(() => {
    const e = this.resource.error();
    return e ? errorMessage(e) : '';
  });

  protected readonly formatInteger = formatInteger;

  protected valueOf(event: Event): string {
    return (event.target as HTMLSelectElement).value;
  }
}
