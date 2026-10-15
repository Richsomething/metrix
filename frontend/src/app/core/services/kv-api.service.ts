import { inject, Injectable, Signal } from '@angular/core';
import { HttpClient, httpResource, HttpResourceRef } from '@angular/common/http';
import { map, Observable } from 'rxjs';
import { ApiResponse } from '../models/dashboard.model';
import {
  KvAdditions,
  KvCabinet,
  KvOptions,
  KvRecommendations,
  KvReviewReport,
  KvSimulation,
} from '../models/kv.model';

const KV_URL = '/api/ml/kv';

function unwrap<T>(response: ApiResponse<T>): T {
  if (!response.success || response.data === undefined) {
    throw new Error(response.error ?? 'Пустой ответ ML-сервиса');
  }
  return response.data;
}

/** АВ cabinet API (via the Node proxy). All numbers are computed by the Python service. */
@Injectable({ providedIn: 'root' })
export class KvApiService {
  private readonly http = inject(HttpClient);

  options(): HttpResourceRef<ApiResponse<KvOptions> | undefined> {
    return httpResource<ApiResponse<KvOptions>>(() => `${KV_URL}/options`);
  }

  /** No request until both agent and quarter are known. */
  cabinet(
    agent: Signal<string>,
    quarter: Signal<string>,
  ): HttpResourceRef<ApiResponse<KvCabinet> | undefined> {
    return httpResource<ApiResponse<KvCabinet>>(() =>
      agent() && quarter()
        ? { url: `${KV_URL}/cabinet`, params: { agent: agent(), quarter: quarter() } }
        : undefined,
    );
  }

  /** Main-page advice for the open quarter; no request until the agent is known. */
  recommendations(
    agent: Signal<string>,
  ): HttpResourceRef<ApiResponse<KvRecommendations> | undefined> {
    return httpResource<ApiResponse<KvRecommendations>>(() =>
      agent() ? { url: `${KV_URL}/recommendations`, params: { agent: agent() } } : undefined,
    );
  }

  simulate(agent: string, quarter: string, additions: KvAdditions): Observable<KvSimulation> {
    return this.http
      .post<ApiResponse<KvSimulation>>(`${KV_URL}/simulate`, { agent, quarter, ...additions })
      .pipe(map(unwrap));
  }

  review(agent: string, quarter: string): Observable<KvReviewReport> {
    return this.http
      .post<ApiResponse<KvReviewReport>>('/api/ml/agents/kv-review', { agent, quarter })
      .pipe(map(unwrap));
  }

  exportUrl(agent: string, quarter: string, additions: KvAdditions | null): string {
    const params = new URLSearchParams({ agent, quarter });
    if (additions) {
      params.set('extra_kasko', String(additions.extra_kasko));
      params.set('extra_priority', String(additions.extra_priority));
      if (additions.prolonged !== null) params.set('prolonged', String(additions.prolonged));
      if (additions.due !== null) params.set('due', String(additions.due));
    }
    return `${KV_URL}/export?${params.toString()}`;
  }
}
