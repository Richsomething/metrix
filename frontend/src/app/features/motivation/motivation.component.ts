import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  inject,
  linkedSignal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { dataOf, errorMessage } from '../../core/services/bonus-api.service';
import { KvApiService } from '../../core/services/kv-api.service';
import {
  KvAdditions,
  KvPlanOption,
  KvPlanStep,
  KvRate,
  KvReviewReport,
  KvScenario,
  KvSimulation,
} from '../../core/models/kv.model';
import { formatInteger } from '../../shared/utils/format';

const pctFormat = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 });
const KASKO = 'КАСКО';

type RunState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'done'; result: T }
  | { status: 'error'; message: string };

const SCENARIOS: KvScenario[] = ['cautious', 'base', 'optimistic'];

interface IndicatorRow {
  title: string;
  rule: string;
  current: string;
  next: string;
  currentBonus: string;
  nextBonus: string;
}

/** «Моя мотивация»: АВ rates by line (base + Доп.АВ1–3) now and next quarter, income, plan, «what if». */
@Component({
  selector: 'app-motivation',
  templateUrl: './motivation.component.html',
  styleUrl: './motivation.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MotivationComponent {
  private readonly api = inject(KvApiService);
  private readonly destroyRef = inject(DestroyRef);

  private readonly optionsRef = this.api.options();
  protected readonly options = computed(() => dataOf(this.optionsRef));

  protected readonly agent = linkedSignal(() => this.options()?.agents[0] ?? '');
  protected readonly quarter = linkedSignal(() => this.options()?.currentQuarter ?? '');

  private readonly cabinetRef = this.api.cabinet(this.agent, this.quarter);
  protected readonly cabinet = computed(() => dataOf(this.cabinetRef));
  protected readonly loading = computed(() => this.cabinetRef.isLoading() && !this.cabinet());
  protected readonly error = computed(() => {
    const e = this.optionsRef.error() ?? this.cabinetRef.error();
    return e ? errorMessage(e) : '';
  });

  protected readonly isCurrent = computed(() => this.quarter() === this.options()?.currentQuarter);

  // calculator inputs: ₽, ₽, contracts; empty prolongation fields = not set
  private readonly key = () => this.agent() + this.quarter();
  protected readonly extraKasko = linkedSignal({ source: this.key, computation: () => 0 });
  protected readonly extraPriority = linkedSignal({ source: this.key, computation: () => 0 });
  protected readonly prolonged = linkedSignal({ source: this.key, computation: () => '' });
  protected readonly due = linkedSignal({ source: this.key, computation: () => '' });

  protected readonly simulation = linkedSignal<string, RunState<KvSimulation>>({
    source: this.key,
    computation: () => ({ status: 'idle' }),
  });
  protected readonly review = linkedSignal<string, RunState<KvReviewReport>>({
    source: this.key,
    computation: () => ({ status: 'idle' }),
  });

  protected readonly additions = computed<KvAdditions>(() => ({
    extra_kasko: Math.max(0, this.extraKasko() || 0),
    extra_priority: Math.max(0, this.extraPriority() || 0),
    prolonged: this.count(this.prolonged()),
    due: this.count(this.due()),
  }));

  protected readonly exportHref = computed(() => {
    const sim = this.simulation();
    return this.api.exportUrl(
      this.agent(),
      this.quarter(),
      sim.status === 'done' ? this.additions() : null,
    );
  });

  /** Lines with this quarter's components and both totals. */
  protected readonly rateRows = computed(() => {
    const c = this.cabinet();
    if (!c) return [];
    const next = new Map(c.nextRate.rates.map((r) => [r.line, r]));
    return c.currentRate.rates.map((r) => ({
      ...r,
      nextTotal: next.get(r.line)?.total ?? null,
      nextCapped: next.get(r.line)?.capped ?? false,
    }));
  });

  protected readonly kasko = computed(() => {
    const c = this.cabinet();
    if (!c) return null;
    const find = (rate: KvRate) => rate.rates.find((r) => r.line === KASKO) ?? null;
    return { current: find(c.currentRate), next: find(c.nextRate) };
  });

  protected readonly indicatorRows = computed<IndicatorRow[]>(() => {
    const c = this.cabinet();
    if (!c) return [];
    const cur = c.currentRate;
    const nxt = c.nextRate;
    const prol = (r: KvRate) => {
      const p = r.metrics.prolongation;
      const done = p.prolonged === null ? '?' : formatInteger(p.prolonged);
      const due = `${p.dueEstimated ? '≈' : ''}${formatInteger(p.due)}`;
      return p.rate === null
        ? `${done} из ${due} — ${p.missing}`
        : `${this.pct(p.rate)} (${done} из ${due})`;
    };
    const dyn = (r: KvRate) =>
      `${this.signedPct(r.metrics.dynamics)} к ${r.previous}${r.metrics.dynamicsFloorApplied ? ' (база 100 000 ₽)' : ''}`;
    return [
      {
        title: 'ДВС отчётного квартала',
        rule: `шкала КАСКО: ${this.groupText(cur)}`,
        current: this.money(cur.metrics.dvs),
        next: this.money(nxt.metrics.dvs),
        currentBonus: this.pct(cur.components.kaskoBase.rate),
        nextBonus: this.pct(nxt.components.kaskoBase.rate),
      },
      {
        title: 'Динамика ДВС — Доп.АВ1',
        rule: 'шкала по номеру отчётного квартала',
        current: dyn(cur),
        next: dyn(nxt),
        currentBonus: this.pp(cur.components.d1.value),
        nextBonus: this.pp(nxt.components.d1.value),
      },
      {
        title: 'Доля приоритетных — Доп.АВ2',
        rule: `> ${this.pct(cur.components.d2.above)}`,
        current: this.pct(cur.metrics.penetration),
        next: this.pct(nxt.metrics.penetration),
        currentBonus: this.pp(cur.components.d2.value),
        nextBonus: this.pp(nxt.components.d2.value),
      },
      {
        title: 'Пролонгация — Доп.АВ3',
        rule: `≥ ${this.pct(cur.components.d3.atLeast)}`,
        current: prol(cur),
        next: prol(nxt),
        currentBonus: this.pp(cur.components.d3.value),
        nextBonus: this.pp(nxt.components.d3.value),
      },
    ];
  });

  protected readonly scenarioRows = computed(() => {
    const c = this.cabinet();
    if (!c) return [];
    return SCENARIOS.map((s) => ({
      title: c.income.next[s].scenarioTitle,
      kasko: c.nextRateByScenario[s].find((r) => r.line === KASKO)?.total ?? null,
      current: c.income.current[s].kv,
      next: c.income.next[s].kv,
    }));
  });

  protected readonly formatInteger = formatInteger;

  protected money(value: number | null | undefined): string {
    return value === null || value === undefined ? '—' : `${formatInteger(value)} ₽`;
  }

  protected pct(value: number | null | undefined): string {
    return value === null || value === undefined ? '—' : `${pctFormat.format(value * 100)}%`;
  }

  protected signedPct(value: number): string {
    return `${value >= 0 ? '+' : ''}${pctFormat.format(value * 100)}%`;
  }

  protected pp(value: number | null | undefined): string {
    return value ? `+${pctFormat.format(value * 100)} п.п.` : '0';
  }

  protected groupText(rate: KvRate): string {
    const kb = rate.components.kaskoBase;
    if (!kb.group) return 'группа не задана';
    return kb.scaleGroup && kb.scaleGroup !== kb.group
      ? `${kb.group} → ${kb.scaleGroup}*`
      : kb.group;
  }

  protected stepNeed(step: KvPlanStep): string {
    const n = step.needs;
    if (step.blocked) return step.blocked;
    if (n.dvs !== undefined) return `+${this.money(n.dvs)} ДВС`;
    if (n.priority !== undefined) return `+${this.money(n.priority)} приоритетных`;
    if (n.prolonged !== undefined) {
      return `${formatInteger(n.prolonged)} из ${n.dueEstimated ? '≈' : ''}${formatInteger(n.due ?? 0)} договоров`;
    }
    return '—';
  }

  protected stepChange(step: KvPlanStep): string {
    return step.component === 'kaskoBase'
      ? `${this.pct(step.from)} → ${this.pct(step.to)}`
      : `${this.pp(step.from)} → ${this.pp(step.to)}`;
  }

  protected contractsText(option: KvPlanOption): string {
    return `≈ ${option.contracts.kasko.contracts ?? 0} + ${option.contracts.priority.contracts ?? 0}`;
  }

  protected numberValue(event: Event): number {
    return Number((event.target as HTMLInputElement).value);
  }

  protected textValue(event: Event): string {
    return (event.target as HTMLInputElement | HTMLSelectElement).value;
  }

  protected applyOption(option: KvPlanOption): void {
    this.extraKasko.set(option.kasko);
    this.extraPriority.set(option.priority);
    this.prolonged.set(option.prolonged === null ? '' : String(option.prolonged));
    this.runSimulation();
  }

  protected runSimulation(): void {
    if (!this.isCurrent()) return;
    this.simulation.set({ status: 'loading' });
    this.api
      .simulate(this.agent(), this.quarter(), this.additions())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => this.simulation.set({ status: 'done', result }),
        error: (e: unknown) => this.simulation.set({ status: 'error', message: errorMessage(e) }),
      });
  }

  protected runReview(): void {
    this.review.set({ status: 'loading' });
    this.api
      .review(this.agent(), this.quarter())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => this.review.set({ status: 'done', result }),
        error: (e: unknown) => this.review.set({ status: 'error', message: errorMessage(e) }),
      });
  }

  private count(text: string): number | null {
    const value = text.trim();
    return value === '' ? null : Math.max(0, Math.round(Number(value) || 0));
  }
}
