/** 后端 API 客户端（与 apps/api 的 /api/v1 对齐）。 */

const BASE = '/api/v1'

export type ContentType =
  | 'flash'
  | 'article'
  | 'announcement'
  | 'policy'
  | 'research_report'
  | 'interactive_qa'
  | 'social_post'
  | 'market_data'

export type ActionType = 'read' | 'star' | 'unstar' | 'rate' | 'hide' | 'block_source'

export interface NewsItem {
  id: string
  title: string
  summary: string | null
  source_name: string | null
  url: string | null
  content_type: ContentType
  published_at: string
  importance: number | null
  cluster_id: string | null
  industries: string[]
  market_scope: string[]
  source_count: number
}

export interface SourceRef {
  connector_id: string
  external_id: string
  source_name: string | null
  url: string | null
}

export interface NewsDetail extends NewsItem {
  content: string | null
  source_refs: SourceRef[]
  siblings: { id: string; title: string; source_name: string | null; url: string | null }[]
}

export interface Connector {
  id: string
  key: string
  display_name: string
  status: string
  config: Record<string, unknown>
  capability: {
    content_types: string[]
    supports_incremental: boolean
    supports_backfill: boolean
    rate_limit_per_min: number | null
    requires_credentials: boolean
  }
  schedule_cron: string | null
  next_run_at: string | null
  last_run_at: string | null
  consecutive_failures: number
  last_error: string | null
}

export interface AvailableConnector {
  key: string
  name: string
  capability: Connector['capability']
}

export interface SyncStats {
  status: string
  run_id: string
  fetched: number
  inserted: number
  duplicated: number
  failed_segments: { api: string; error: string }[]
  empty_reason?: string
}

export interface SyncRun {
  id: string
  status: string
  fetched: number
  inserted: number
  duplicated: number
  error: string | null
  started_at: string
  finished_at: string | null
}

export interface ProbeResult {
  ok: boolean
  rows: number
  reason: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}${detail ? ` — ${detail}` : ''}`)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export interface NewsQuery {
  content_type?: string
  industry?: string
  since?: string
  until?: string
  limit?: number
  offset?: number
}

export const api = {
  listNews: (q: NewsQuery) =>
    request<NewsItem[]>(
      '/news?' + new URLSearchParams(compact({ ...q } as Record<string, unknown>)),
    ),

  getNews: (id: string) => request<NewsDetail>(`/news/${id}`),

  createAction: (newsId: string, action: ActionType, rating?: number) =>
    request<{ id: string; action: string; updated: boolean }>(`/news/${newsId}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action, rating }),
    }),

  availableConnectors: () => request<AvailableConnector[]>('/connectors/available'),

  listConnectors: () => request<Connector[]>('/connectors'),

  createConnector: (key: string, config?: Record<string, unknown>) =>
    request<Connector>('/connectors', {
      method: 'POST',
      body: JSON.stringify({ key, config: config ?? {} }),
    }),

  deleteConnector: (id: string) => request<void>(`/connectors/${id}`, { method: 'DELETE' }),

  validateConnector: (id: string) =>
    request<{ ok: boolean; message: string }>(`/connectors/${id}/validate`, { method: 'POST' }),

  syncConnector: (id: string, window?: { start: string; end: string }) =>
    request<SyncStats>(`/connectors/${id}/sync`, {
      method: 'POST',
      body: JSON.stringify(
        window ? { window_start: window.start, window_end: window.end } : {},
      ),
    }),

  listRuns: (id: string) => request<SyncRun[]>(`/connectors/${id}/runs`),
}

function compact(obj: Record<string, unknown>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(obj)
      .filter(([, v]) => v !== undefined && v !== null && v !== '')
      .map(([k, v]) => [k, String(v)]),
  )
}
