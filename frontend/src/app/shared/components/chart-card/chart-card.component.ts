import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';
import type { EChartsOption } from 'echarts';
import { ChartComponent } from '../chart/chart.component';

export interface TableData {
  columns: string[];
  rows: (string | number)[][];
}

export interface ChartView {
  option: EChartsOption;
  table: TableData;
}

/** Card with a chart and an accessible table view of the same data. */
@Component({
  selector: 'app-chart-card',
  imports: [ChartComponent],
  template: `
    <header class="head">
      <div>
        <h3>{{ title() }}</h3>
        @if (subtitle()) {
          <p class="subtitle">{{ subtitle() }}</p>
        }
      </div>
      <button
        type="button"
        class="toggle"
        (click)="showTable.set(!showTable())"
        [attr.aria-pressed]="showTable()"
      >
        {{ showTable() ? 'График' : 'Таблица' }}
      </button>
    </header>

    @if (isEmpty()) {
      <p class="empty" [style.height]="height()">Нет данных для выбранных фильтров</p>
    } @else if (showTable()) {
      <div class="table-wrap" [style.max-height]="height()">
        <table>
          <thead>
            <tr>
              @for (column of view().table.columns; track $index) {
                <th scope="col">{{ column }}</th>
              }
            </tr>
          </thead>
          <tbody>
            @for (row of view().table.rows; track $index) {
              <tr>
                @for (cell of row; track $index) {
                  <td>{{ cell }}</td>
                }
              </tr>
            }
          </tbody>
        </table>
      </div>
    } @else {
      <app-chart [option]="view().option" [label]="title()" [style.--chart-height]="height()" />
    }
  `,
  styleUrl: './chart-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ChartCardComponent {
  readonly title = input.required<string>();
  readonly subtitle = input('');
  readonly view = input.required<ChartView>();
  readonly height = input('300px');

  protected readonly showTable = signal(false);
  protected readonly isEmpty = computed(() => this.view().table.rows.length === 0);
}
