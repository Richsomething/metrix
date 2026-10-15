import { inject, Injectable, Signal } from '@angular/core';
import { HttpClient, HttpErrorResponse, httpResource, HttpResourceRef } from '@angular/common/http';
import { map, Observable } from 'rxjs';
import { ApiResponse } from '../models/dashboard.model';
import {
  AskReport,
  BonusFilters,
  BonusForecast,
  BonusSummary,
  ForecastInfo,
  ModelMetrics,
  ScenarioSet,
  PlanRow,
  ReviewReport,
} from '../models/bonus.model';

const ML_URL = '/api/ml';

function activeParams(filters: BonusFilters): Record<string, string> {
  return Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== ''));
}

function unwrap<T>(response: ApiResponse<T>): T {
  if (!response.success || response.data === undefined) {
    throw new Error(response.error ?? 'Пустой ответ ML-сервиса');
  }
  return response.data;
}

/** `value()` of a resource in error state throws; read it only when a value exists. */
export function dataOf<T>(ref: HttpResourceRef<ApiResponse<T> | undefined>): T | undefined {
  return ref.hasValue() ? ref.value()?.data : undefined;
}

export function errorMessage(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    const serverText = (error.error as ApiResponse<unknown> | null)?.error;
    if (serverText) return serverText;
    return error.status === 0
      ? 'Сервер не отвечает: проверьте, что backend (порт 3000) запущен'
      : `Ошибка сервера (HTTP ${error.status})`;
  }
  return error instanceof Error ? error.message : 'Неизвестная ошибка';
}

/** ML service (via the Node proxy): model plans, bonuses and the AI agents. */
@Injectable({ providedIn: 'root' })
export class BonusApiService {
  private readonly http = inject(HttpClient);

  plans(filters: Signal<BonusFilters>): HttpResourceRef<ApiResponse<PlanRow[]> | undefined> {
    return httpResource<ApiResponse<PlanRow[]>>(() => ({
      url: `${ML_URL}/plans`,
      params: activeParams(filters()),
    }));
  }

  bonuses(filters: Signal<BonusFilters>): HttpResourceRef<ApiResponse<BonusSummary[]> | undefined> {
    return httpResource<ApiResponse<BonusSummary[]>>(() => ({
      url: `${ML_URL}/bonuses`,
      params: activeParams(filters()),
    }));
  }

  model(): HttpResourceRef<ApiResponse<ModelMetrics> | undefined> {
    return httpResource<ApiResponse<ModelMetrics>>(() => `${ML_URL}/model`);
  }

  forecast(agent: Signal<string>): HttpResourceRef<ApiResponse<ForecastInfo> | undefined> {
    return httpResource<ApiResponse<ForecastInfo>>(() => ({
      url: `${ML_URL}/forecast`,
      params: activeParams({ agent: agent(), year: '' }),
    }));
  }

  bonusForecast(agent: Signal<string>): HttpResourceRef<ApiResponse<BonusForecast> | undefined> {
    return httpResource<ApiResponse<BonusForecast>>(() =>
      agent() ? { url: `${ML_URL}/bonus/forecast`, params: { agent: agent() } } : undefined,
    );
  }

  /** Request waits until an agent is known (undefined request = no call). */
  scenarios(agent: Signal<string>): HttpResourceRef<ApiResponse<ScenarioSet> | undefined> {
    return httpResource<ApiResponse<ScenarioSet>>(() =>
      agent() ? { url: `${ML_URL}/bonus/scenarios`, params: { agent: agent() } } : undefined,
    );
  }

  review(agent: string, quarter: string): Observable<ReviewReport> {
    return this.http
      .post<ApiResponse<ReviewReport>>(`${ML_URL}/agents/review`, { agent, quarter })
      .pipe(map(unwrap));
  }

  ask(question: string): Observable<AskReport> {
    return this.http
      .post<ApiResponse<AskReport>>(`${ML_URL}/agents/ask`, { question })
      .pipe(map(unwrap));
  }
}
