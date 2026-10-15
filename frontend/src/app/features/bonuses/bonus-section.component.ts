import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { BonusApiService, dataOf, errorMessage } from '../../core/services/bonus-api.service';
import { ThemeService } from '../../core/services/theme.service';
import { BonusFilters } from '../../core/models/bonus.model';
import { ChartCardComponent } from '../../shared/components/chart-card/chart-card.component';
import { KpiTileComponent } from '../../shared/components/kpi-tile/kpi-tile.component';
import {
  formatCompact,
  formatInteger,
  formatMoney,
  formatPercent,
} from '../../shared/utils/format';
import { AiAgentsPanelComponent } from './ai-agents-panel/ai-agents-panel.component';
import { BonusForecastComponent } from './bonus-forecast.component';
import {
  bonusByAgentChart,
  completedTotals,
  modelQualityChart,
  planFactChart,
  RECOMMENDED_PLAN_LABEL,
} from './bonus-charts';

const ROW_HEIGHT_PX = 34;
const MIN_BAR_CHART_PX = 200;

@Component({
  selector: 'app-bonus-section',
  imports: [ChartCardComponent, KpiTileComponent, AiAgentsPanelComponent, BonusForecastComponent],
  templateUrl: './bonus-section.component.html',
  styleUrl: './bonus-section.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BonusSectionComponent {
  readonly agent = input('');
  readonly year = input('');
  /** The main page shows the forecast chart itself; the analytics tab passes false. */
  readonly withForecast = input(true);

  private readonly api = inject(BonusApiService);
  private readonly tokens = inject(ThemeService).tokens;
  private readonly filters = computed<BonusFilters>(() => ({
    agent: this.agent(),
    year: this.year(),
  }));

  protected readonly model = this.api.model();
  protected readonly plans = this.api.plans(this.filters);
  protected readonly bonuses = this.api.bonuses(this.filters);
  protected readonly forecast = this.api.forecast(this.agent);

  protected readonly metrics = computed(() => dataOf(this.model));
  /** Scenario agent: the dashboard filter, otherwise the first agent known to the model. */
  protected readonly scenarioAgent = computed(
    () => this.agent() || this.metrics()?.agents[0] || '',
  );
  protected readonly scenarios = this.api.scenarios(this.scenarioAgent);

  protected readonly planLabel = RECOMMENDED_PLAN_LABEL;
  protected readonly formatInteger = formatInteger;
  protected readonly formatMoney = formatMoney;
  protected readonly formatPercent = formatPercent;

  protected readonly errorMessage = computed(() => {
    const error =
      this.model.error() ?? this.plans.error() ?? this.bonuses.error() ?? this.forecast.error();
    return error ? errorMessage(error) : '';
  });
  protected readonly scenarioError = computed(() => {
    const error = this.scenarios.error();
    return error ? errorMessage(error) : '';
  });
  protected readonly forecastData = computed(() => dataOf(this.forecast));
  protected readonly scenarioData = computed(() => dataOf(this.scenarios));
  protected readonly isLoading = computed(() => this.model.isLoading() || this.plans.isLoading());

  protected readonly chosenTitle = computed(() => {
    const m = this.metrics();
    return m?.scores.find((s) => s.name === m.chosen)?.title ?? '';
  });

  protected readonly completed = computed(() => {
    const plans = dataOf(this.plans);
    const bonuses = dataOf(this.bonuses);
    const m = this.metrics();
    if (!plans || !bonuses || !m) return null;

    const totals = completedTotals(plans);
    if (totals.length === 0)
      return { empty: true as const, firstPlanned: m.plannedQuarters[0] ?? '' };

    const t = this.tokens();
    const plan = totals.reduce((sum, q) => sum + q.plan, 0);
    const fact = totals.reduce((sum, q) => sum + q.fact, 0);
    const best = m.scores.find((s) => s.name === m.chosen);
    return {
      empty: false as const,
      kpis: [
        {
          label: 'Премии за период',
          value: formatMoney(bonuses.reduce((sum, b) => sum + b.bonus, 0)),
          hint: `${totals.length} завершённых кв.`,
        },
        {
          label: 'Выполнение рекомендуемого плана',
          value: formatPercent((fact / plan) * 100),
          hint: `факт ${formatCompact(fact)} / план ${formatCompact(plan)}`,
        },
        {
          label: 'Ошибка плана (WAPE)',
          value: best ? formatPercent(best.wape * 100) : '—',
          hint: 'бэктест на синтетическом наборе',
        },
      ],
      planFact: planFactChart(plans, t),
      bonusByAgent: bonusByAgentChart(bonuses, t),
      bonusHeight: `${Math.max(MIN_BAR_CHART_PX, bonuses.length * ROW_HEIGHT_PX + 40)}px`,
      quality: modelQualityChart(m.scores, t),
    };
  });
}
