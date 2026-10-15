import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  inject,
  input,
  linkedSignal,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { BonusApiService, errorMessage } from '../../../core/services/bonus-api.service';
import { AskReport, ReviewReport, ToolCall } from '../../../core/models/bonus.model';
import { formatInteger, formatMoney, formatPercent } from '../../../shared/utils/format';

type RunState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'done'; result: T }
  | { status: 'error'; message: string };

const MIN_QUESTION_LENGTH = 3;
const ROLE_LABELS: Record<string, string> = {
  analyst: 'Аналитик',
  motivator: 'Мотиватор',
  auditor: 'Контролёр',
  assistant: 'Ассистент',
};

/** Unique tool names per agent role, in call order. */
function toolSummary(calls: ToolCall[]): { role: string; tools: string }[] {
  const byRole = calls.reduce((acc, call) => {
    const names = acc.get(call.role) ?? [];
    return acc.set(call.role, names.includes(call.name) ? names : [...names, call.name]);
  }, new Map<string, string[]>());
  return [...byRole.entries()].map(([role, names]) => ({
    role: ROLE_LABELS[role] ?? role,
    tools: names.join(', '),
  }));
}

@Component({
  selector: 'app-ai-agents-panel',
  templateUrl: './ai-agents-panel.component.html',
  styleUrl: './ai-agents-panel.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AiAgentsPanelComponent {
  readonly agents = input.required<string[]>();
  readonly quarters = input.required<string[]>();
  readonly defaultAgent = input('');

  private readonly api = inject(BonusApiService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly selectedAgent = linkedSignal(
    () => this.defaultAgent() || this.agents()[0] || '',
  );
  protected readonly selectedQuarter = linkedSignal(() => this.quarters().at(-1) ?? '');
  protected readonly question = signal('');

  protected readonly review = signal<RunState<ReviewReport>>({ status: 'idle' });
  protected readonly answer = signal<RunState<AskReport>>({ status: 'idle' });

  protected readonly reviewTools = computed(() => {
    const state = this.review();
    return state.status === 'done' ? toolSummary(state.result.tool_calls) : [];
  });
  protected readonly answerTools = computed(() => {
    const state = this.answer();
    return state.status === 'done' ? toolSummary(state.result.tool_calls) : [];
  });
  protected readonly canAsk = computed(
    () =>
      this.question().trim().length >= MIN_QUESTION_LENGTH && this.answer().status !== 'loading',
  );

  protected readonly formatMoney = formatMoney;
  protected readonly formatInteger = formatInteger;
  protected readonly formatPercent = formatPercent;

  protected selectValue(event: Event): string {
    return (event.target as HTMLSelectElement | HTMLTextAreaElement).value;
  }

  protected runReview(): void {
    const agent = this.selectedAgent();
    const quarter = this.selectedQuarter();
    if (!agent || !quarter) return;

    this.review.set({ status: 'loading' });
    this.api
      .review(agent, quarter)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => this.review.set({ status: 'done', result }),
        error: (error: unknown) =>
          this.review.set({ status: 'error', message: errorMessage(error) }),
      });
  }

  protected runAsk(): void {
    if (!this.canAsk()) return;

    this.answer.set({ status: 'loading' });
    this.api
      .ask(this.question().trim())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (result) => this.answer.set({ status: 'done', result }),
        error: (error: unknown) =>
          this.answer.set({ status: 'error', message: errorMessage(error) }),
      });
  }
}
