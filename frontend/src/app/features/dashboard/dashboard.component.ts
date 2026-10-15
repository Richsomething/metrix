import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  linkedSignal,
  signal,
} from '@angular/core';
import { DashboardApiService } from '../../core/services/dashboard-api.service';
import { ThemeService } from '../../core/services/theme.service';
import { DashboardData, DashboardFilters, EMPTY_FILTERS } from '../../core/models/dashboard.model';
import { ChartCardComponent } from '../../shared/components/chart-card/chart-card.component';
import { KpiTileComponent } from '../../shared/components/kpi-tile/kpi-tile.component';
import { formatCompact, formatInteger } from '../../shared/utils/format';
import { FilterBarComponent, FilterChange } from './filter-bar/filter-bar.component';
import { BonusSectionComponent } from '../bonuses/bonus-section.component';
import { MotivationComponent } from '../motivation/motivation.component';
import { HomeComponent } from '../home/home.component';
import {
  agentHeatmapChart,
  agentsChart,
  branchesChart,
  groupsChart,
  linesChart,
  productsChart,
  quarterlyChart,
  tenureChart,
} from './chart-options/collections.charts';
import {
  prolongByAgentChart,
  prolongByMonthChart,
  prolongByProductChart,
} from './chart-options/prolongation.charts';

type Tab = 'home' | 'av' | 'analytics';
const TABS: { id: Tab; title: string }[] = [
  { id: 'home', title: 'Главная' },
  { id: 'av', title: 'Расчёт АВ' },
  { id: 'analytics', title: 'Аналитика' },
];

/** The open tab survives a reload through the URL hash (#av, #analytics). */
function tabFromHash(): Tab {
  const hash = typeof location === 'undefined' ? '' : location.hash.slice(1);
  return TABS.some((t) => t.id === hash) ? (hash as Tab) : 'home';
}

const ROW_HEIGHT_PX = 34;
const MIN_BAR_CHART_PX = 220;

/** Height that keeps each bar row readable regardless of how many categories survive the filters. */
const barsHeight = (rows: number): string =>
  `${Math.max(MIN_BAR_CHART_PX, rows * ROW_HEIGHT_PX + 40)}px`;

@Component({
  selector: 'app-dashboard',
  imports: [
    FilterBarComponent,
    KpiTileComponent,
    ChartCardComponent,
    BonusSectionComponent,
    MotivationComponent,
    HomeComponent,
  ],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardComponent {
  private readonly api = inject(DashboardApiService);
  private readonly tokens = inject(ThemeService).tokens;

  protected readonly tabs = TABS;
  protected readonly tab = signal<Tab>(tabFromHash());

  protected readonly filters = signal<DashboardFilters>(EMPTY_FILTERS);
  protected readonly filterOptions = this.api.filterOptions();
  protected readonly dashboard = this.api.dashboard(this.filters);

  /** Keeps the previous result on screen while a new filter combination loads. */
  protected readonly data = linkedSignal<DashboardData | undefined, DashboardData | undefined>({
    source: () => (this.dashboard.hasValue() ? this.dashboard.value()?.data : undefined),
    computation: (next, previous) => next ?? previous?.value,
  });

  protected readonly errorMessage = computed(() => {
    if (!this.dashboard.error() && !this.filterOptions.error()) return '';
    return 'Не удалось загрузить данные. Проверьте, что backend запущен (npm start в папке backend).';
  });

  protected readonly kpis = computed(() => {
    const k = this.data()?.kpi;
    if (!k) return [];
    return [
      { label: 'Сборы всего', value: formatCompact(k.total), hint: formatInteger(k.total) },
      { label: 'Договоров', value: formatInteger(k.contracts), hint: 'уникальных' },
      {
        label: 'Средний сбор на договор',
        value: formatCompact(k.avgPerContract),
        hint: formatInteger(k.avgPerContract),
      },
      { label: 'Возвраты', value: formatCompact(k.refunds), hint: 'сумма отрицательных сборов' },
      { label: 'К пролонгации', value: formatInteger(k.prolongationsDue), hint: 'договоров' },
    ];
  });

  protected readonly charts = computed(() => {
    const d = this.data();
    const t = this.tokens();
    if (!d) return null;
    return {
      quarterly: quarterlyChart(d.byQuarter, t),
      lines: linesChart(d.byQuarterLine, t),
      agents: agentsChart(d.byAgent, t),
      agentsHeight: barsHeight(d.byAgent.length),
      branches: branchesChart(d.byBranch, t),
      groups: groupsChart(d.byGroup, t),
      products: productsChart(d.topProducts, t),
      productsHeight: barsHeight(d.topProducts.length),
      heatmap: agentHeatmapChart(d.agentQuarterHeatmap, t),
      heatmapHeight: `${Math.max(MIN_BAR_CHART_PX, d.agentQuarterHeatmap.agents.length * 40 + 90)}px`,
      tenure: tenureChart(d.agentTenure, t),
      prolongMonth: prolongByMonthChart(d.prolongByMonth, t),
      prolongAgent: prolongByAgentChart(d.prolongByAgent, t),
      prolongAgentHeight: barsHeight(d.prolongByAgent.length),
      prolongProduct: prolongByProductChart(d.prolongByProduct, t),
      prolongProductHeight: barsHeight(d.prolongByProduct.length),
    };
  });

  protected onFilterChange({ key, value }: FilterChange): void {
    this.filters.update((current) => ({ ...current, [key]: value }));
  }

  protected resetFilters(): void {
    this.filters.set(EMPTY_FILTERS);
  }

  protected select(tab: Tab): void {
    this.tab.set(tab);
    history.replaceState(null, '', tab === 'home' ? location.pathname : `#${tab}`);
  }
}
