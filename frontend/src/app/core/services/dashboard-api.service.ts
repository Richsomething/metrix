import { Injectable, Signal } from '@angular/core';
import { httpResource, HttpResourceRef } from '@angular/common/http';
import {
  ApiResponse,
  DashboardData,
  DashboardFilters,
  FilterOptions,
} from '../models/dashboard.model';

const API_URL = '/api';

/** Drops empty filters so the query string carries only active ones. */
function activeParams(filters: DashboardFilters): Record<string, string> {
  return Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== ''));
}

/** Resources must be created in an injection context (component field initializers). */
@Injectable({ providedIn: 'root' })
export class DashboardApiService {
  filterOptions(): HttpResourceRef<ApiResponse<FilterOptions> | undefined> {
    return httpResource<ApiResponse<FilterOptions>>(() => `${API_URL}/filters`);
  }

  dashboard(
    filters: Signal<DashboardFilters>,
  ): HttpResourceRef<ApiResponse<DashboardData> | undefined> {
    return httpResource<ApiResponse<DashboardData>>(() => ({
      url: `${API_URL}/dashboard`,
      params: activeParams(filters()),
    }));
  }
}
