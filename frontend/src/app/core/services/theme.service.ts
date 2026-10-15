import { Injectable, signal } from '@angular/core';

export interface ChartTokens {
  surface: string;
  textPrimary: string;
  textSecondary: string;
  muted: string;
  grid: string;
  axis: string;
  border: string;
  /** Categorical slots in fixed, CVD-validated order — never cycled. */
  series: readonly string[];
  /** Sequential blue ramp, near-zero first (recedes toward the surface). */
  sequential: readonly string[];
}

const LIGHT: ChartTokens = {
  surface: '#fcfcfb',
  textPrimary: '#0b0b0b',
  textSecondary: '#52514e',
  muted: '#898781',
  grid: '#e1e0d9',
  axis: '#c3c2b7',
  border: 'rgba(11,11,11,0.10)',
  series: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948'],
  sequential: ['#cde2fb', '#86b6ef', '#3987e5', '#1c5cab', '#0d366b'],
};

/** Chart colors. The app has a single light theme. */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly tokens = signal<ChartTokens>(LIGHT).asReadonly();
}
