import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { DashboardFilters, FilterKey, FilterOptions } from '../../../core/models/dashboard.model';

interface FilterField {
  key: FilterKey;
  label: string;
  options: string[];
}

export interface FilterChange {
  key: FilterKey;
  value: string;
}

/** One row of dimension filters above the charts. */
@Component({
  selector: 'app-filter-bar',
  template: `
    @for (field of fields(); track field.key) {
      <label class="field">
        <span>{{ field.label }}</span>
        <select [value]="value()[field.key]" (change)="onChange(field.key, $event)">
          <option value="">Все</option>
          @for (option of field.options; track option) {
            <option [value]="option" [selected]="option === value()[field.key]">
              {{ option }}
            </option>
          }
        </select>
      </label>
    }
    <button type="button" class="reset" (click)="reset.emit()" [disabled]="!hasActive()">
      Сбросить
    </button>
  `,
  styleUrl: './filter-bar.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FilterBarComponent {
  readonly options = input.required<FilterOptions>();
  readonly value = input.required<DashboardFilters>();
  readonly changed = output<FilterChange>();
  readonly reset = output<void>();

  protected readonly fields = computed<FilterField[]>(() => {
    const o = this.options();
    return [
      { key: 'year', label: 'Год', options: o.years },
      { key: 'group', label: 'Группа филиалов', options: o.groups },
      { key: 'branch', label: 'Филиал', options: o.branches },
      { key: 'agent', label: 'Агент', options: o.agents },
      { key: 'line', label: 'Линия бизнеса', options: o.lines },
    ];
  });

  protected readonly hasActive = computed(() => Object.values(this.value()).some((v) => v !== ''));

  protected onChange(key: FilterKey, event: Event): void {
    this.changed.emit({ key, value: (event.target as HTMLSelectElement).value });
  }
}
