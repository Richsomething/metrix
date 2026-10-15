import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'app-kpi-tile',
  template: `
    <p class="label">{{ label() }}</p>
    <p class="value">{{ value() }}</p>
    @if (hint()) {
      <p class="hint">{{ hint() }}</p>
    }
  `,
  styles: `
    :host {
      display: block;
      padding: 16px;
      background: var(--surface-1);
      border: 1px solid var(--border);
      border-radius: 12px;
    }
    p {
      margin: 0;
    }
    .label {
      font-size: 13px;
      color: var(--text-secondary);
    }
    .value {
      margin-top: 6px;
      font-size: 26px;
      font-weight: 600;
      color: var(--text-primary);
    }
    .hint {
      margin-top: 4px;
      font-size: 12px;
      color: var(--text-muted);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class KpiTileComponent {
  readonly label = input.required<string>();
  readonly value = input.required<string>();
  readonly hint = input('');
}
