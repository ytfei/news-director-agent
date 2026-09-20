/**
 * 后端 API 客户端（与 apps/api 的 /api/v1 对齐）。
 *
 * 领域顺序：资讯 → 素材 →（可选）批注 → 检查 → 选题 → 写作。
 * 素材是中枢对象（docs/06-prototype-to-impl.md §2）：批注挂在素材上，
 * 选题聚合素材，因此 `material` 与 `annotation` 两个 brief 会出现在多处响应里。
 */

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

export type AnnotationStatus =
  | 'draft'
  | 'checking'
  | 'needs_revision'
  | 'passed'
  | 'blocked'
  | 'locked'

export type Verdict = 'passed' | 'needs_revision' | 'blocked'
export type FindingTrack = 'fact' | 'logic' | 'compliance' | 'tone' | 'uniqueness'
export type FindingSeverity = 'blocker' | 'high' | 'medium' | 'low' | 'info'
export type FindingStatus = 'open' | 'accepted' | 'dismissed' | 'ignored'
export type ProjectStatus =
  | 'collecting'
  | 'reviewing'
  | 'ready'
  | 'composing'
  | 'drafting'
  | 'completed'
  | 'archived'
  | 'cancelled'

// ---------------- 资讯 ----------------

export interface MaterialBadge {
  id: string
  score: number
  topics: string[]
  material_date: string
}

export interface AnnotationBrief {
  id: string
  status: AnnotationStatus
  verdict: Verdict | null
  body: string
  excerpt?: string
  version_no: number
  open_findings: number
  last_report_id: string | null
  last_checked_at: string | null
  updated_at: string | null
}

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
  /** M2：列表即带素材/批注徽标，资讯中心不必二次请求 */
  material: MaterialBadge | null
  annotation: AnnotationBrief | null
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
  fact_card?: FactCard | null
}

// ---------------- 素材 / 主题 ----------------

export interface Material {
  id: string
  news_id: string
  material_date: string
  score: number
  status: string
  note: string | null
  topics: string[]
  created_at: string
  updated_at: string
  news: NewsItem | null
  annotation: AnnotationBrief | null
}

export interface Topic {
  id: string
  slug: string
  name: string
  color: string | null
  is_system: boolean
}

export interface MaterialStats {
  date: string
  total: number
  with_annotation: number
  without_annotation: number
  avg_score: number
  by_topic: Record<string, number>
  score_buckets: { ge8: number; '6_7': number; le5: number }
  dates: string[]
}

export interface MaterialQuery {
  date?: string
  min_score?: number
  max_score?: number
  topic?: string[]
  has_annotation?: boolean
  limit?: number
  offset?: number
}

export interface MarkMaterialInput {
  news_id: string
  score?: number
  topics?: string[]
  material_date?: string
  note?: string
}

// ---------------- 体检报告 ----------------

export interface Evidence {
  src?: string
  date?: string
  snippet?: string
  conf?: number
  [k: string]: unknown
}

export interface Finding {
  id: string
  report_id: string
  track: FindingTrack
  severity: FindingSeverity
  status: FindingStatus
  span_start: number
  span_end: number
  quote: string | null
  message: string
  suggestion: string | null
  evidence: Evidence[]
  reason: string | null
}

export interface ReviewReport {
  id: string
  annotation_id: string
  annotation_version_no: number
  verdict: Verdict
  summary: string | null
  findings_count: number
  created_at: string
  annotation: { id: string; body: string; status: AnnotationStatus; version_no: number } | null
  material: { id: string; score: number; material_date: string } | null
  news: { id: string; title: string; source_name: string | null } | null
  findings: Finding[]
}

export interface CheckResult {
  run_id: string
  skipped_material_ids: string[]
  verdict_summary: Record<Verdict, number>
  reports: {
    id: string
    annotation_id: string
    verdict: Verdict
    summary: string | null
    findings_count: number
  }[]
}

export interface FactCardClaim {
  id: string
  seq: number
  claim: string
  status: 'verified' | 'contradicted' | 'unverifiable' | 'outdated'
  confidence: number
  evidence: Evidence[]
}

export interface FactCard {
  id: string
  news_item_id: string
  context_notes: string | null
  related_symbols: string[]
  open_questions: string[]
  status: string
  generated_at: string | null
  claims: FactCardClaim[]
}

// ---------------- 选题 / 提示词 ----------------

export interface Assessment {
  writable: boolean
  mode: 'opinion' | 'digest'
  blocking_reasons: string[]
  stats: {
    materials: number
    with_annotation: number
    without_annotation: number
    with_blocker: number
  }
}

export interface ProjectMaterial extends Material {
  role: 'primary' | 'background'
  sort: number
  has_blocker: boolean
}

/**
 * 选题列表用的**扁平**统计（后端 `bulk_assess`）：
 * 列表页只需要计数，不必为每个选题跑一遍完整 assessment，避免 N+1。
 */
export interface ProjectAssessmentSummary {
  materials: number
  with_annotation: number
  with_blocker: number
  writable: boolean
  mode: 'opinion' | 'digest'
}

export interface ProjectSummary {
  id: string
  title: string
  status: ProjectStatus
  platform: string | null
  target_words: number | null
  updated_at: string
  assessment?: ProjectAssessmentSummary
}

export interface PromptTemplate {
  id: string
  name: string
  category: 'style' | 'structure' | 'persona' | 'taboo'
  version_no: number
  description: string | null
  body?: string
  variables?: string[]
  is_official: boolean
}

export interface ProjectDetail {
  id: string
  title: string
  status: ProjectStatus
  platform: string | null
  target_words: number | null
  require_note: string | null
  prompt_ids: string[]
  prompts: PromptTemplate[]
  created_at: string
  updated_at: string
  materials: ProjectMaterial[]
  assessment: Assessment
}

// ---------------- 数据源（M1） ----------------

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

/** 凭据 / 接口权限探测结果 */
export interface ProbeResult {
  ok: boolean
  rows: number
  reason: string
}

// ---------------- 请求封装 ----------------

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    let message = `${res.status} ${res.statusText}`
    try {
      const parsed = JSON.parse(detail)
      if (parsed?.detail) message = typeof parsed.detail === 'string' ? parsed.detail : JSON.stringify(parsed.detail)
    } catch {
      if (detail) message += ` — ${detail}`
    }
    throw new Error(message)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

function compact(obj: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(obj)) {
    if (v === undefined || v === null || v === '') continue
    out[k] = String(v)
  }
  return out
}

/**
 * 数组参数必须用**重复 key**（`?topic=a&topic=b`），
 * 这是 FastAPI `Query(list[str])` 的解析语义；逗号拼接会被当成单个字符串。
 */
function qs(obj: Record<string, unknown>): URLSearchParams {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(obj)) {
    if (v === undefined || v === null || v === '') continue
    if (Array.isArray(v)) {
      v.filter((x) => x !== undefined && x !== null && x !== '').forEach((x) => p.append(k, String(x)))
    } else {
      p.append(k, String(v))
    }
  }
  return p
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
  // ---- 资讯 ----
  listNews: (q: NewsQuery) =>
    request<NewsItem[]>('/news?' + new URLSearchParams(compact({ ...q } as Record<string, unknown>))),

  getNews: (id: string) => request<NewsDetail>(`/news/${id}`),

  createAction: (newsId: string, action: ActionType, rating?: number) =>
    request<{ id: string; action: string; updated: boolean }>(`/news/${newsId}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action, rating }),
    }),

  getFactCard: (newsId: string) => request<FactCard>(`/news/${newsId}/fact-card`),

  // ---- 素材 ----
  listMaterials: (q: MaterialQuery = {}) =>
    request<Material[]>(
      '/materials?' +
        qs({
          date: q.date,
          min_score: q.min_score,
          max_score: q.max_score,
          topic: q.topic,
          has_annotation: q.has_annotation,
          limit: q.limit ?? 100,
          offset: q.offset,
        }).toString(),
    ),

  materialStats: (date?: string) =>
    request<MaterialStats>('/materials/stats' + (date ? `?date=${date}` : '')),

  getMaterial: (id: string) => request<Material>(`/materials/${id}`),

  markMaterial: (input: MarkMaterialInput) =>
    request<{ created: boolean; material: Material }>('/materials', {
      method: 'POST',
      body: JSON.stringify(input),
    }),

  patchMaterial: (
    id: string,
    input: { score?: number; topics?: string[]; material_date?: string; note?: string },
  ) =>
    request<Material>(`/materials/${id}`, { method: 'PATCH', body: JSON.stringify(input) }),

  deleteMaterial: (id: string) => request<void>(`/materials/${id}`, { method: 'DELETE' }),

  // ---- 主题 ----
  listTopics: () => request<Topic[]>('/topics'),

  createTopic: (name: string) =>
    request<Topic>('/topics', { method: 'POST', body: JSON.stringify({ name }) }),

  // ---- 批注 ----
  getAnnotation: (materialId: string) =>
    request<{ material_id: string; annotation: AnnotationBrief | null; findings: Finding[] }>(
      `/materials/${materialId}/annotation`,
    ),

  putAnnotation: (materialId: string, body: string) =>
    request<{ annotation: AnnotationBrief; version_created: boolean; version_no: number }>(
      `/materials/${materialId}/annotation`,
      { method: 'PUT', body: JSON.stringify({ body }) },
    ),

  annotationVersions: (annotationId: string) =>
    request<{ id: string; version_no: number; body: string; source: string; created_at: string }[]>(
      `/annotations/${annotationId}/versions`,
    ),

  checkAnnotations: (materialIds: string[]) =>
    request<CheckResult>('/annotations/check', {
      method: 'POST',
      body: JSON.stringify({ material_ids: materialIds }),
    }),

  // ---- 体检报告 ----
  listReports: (q: { material_id?: string; annotation_id?: string }) =>
    request<ReviewReport[]>(
      '/reviews?' + new URLSearchParams(compact({ material_id: q.material_id, annotation_id: q.annotation_id })),
    ),

  getReport: (id: string) => request<ReviewReport>(`/reviews/${id}`),

  resolveFinding: (findingId: string, action: FindingStatus, reason?: string) =>
    request<{ finding: Finding; report_verdict: Verdict; needs_recheck: boolean }>(
      `/reviews/findings/${findingId}/resolve`,
      { method: 'POST', body: JSON.stringify({ action, reason }) },
    ),

  // ---- 选题 ----
  listProjects: () => request<ProjectSummary[]>('/projects'),

  createProject: (input: {
    title?: string
    platform?: string
    target_words?: number
    require_note?: string
    prompt_ids?: string[]
    material_ids?: string[]
  }) => request<ProjectDetail>('/projects', { method: 'POST', body: JSON.stringify(input) }),

  getProject: (id: string) => request<ProjectDetail>(`/projects/${id}`),

  patchProject: (id: string, input: Record<string, unknown>) =>
    request<ProjectDetail>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(input) }),

  addProjectMaterials: (id: string, materialIds: string[]) =>
    request<ProjectDetail & { added: number }>(`/projects/${id}/materials`, {
      method: 'POST',
      body: JSON.stringify({ material_ids: materialIds }),
    }),

  removeProjectMaterial: (id: string, materialId: string) =>
    request<void>(`/projects/${id}/materials/${materialId}`, { method: 'DELETE' }),

  composeProject: (id: string) =>
    request<{ run_id: string; status: string; mode: string; note: string }>(
      `/projects/${id}/compose`,
      { method: 'POST' },
    ),

  // ---- 提示词 ----
  listPrompts: () => request<PromptTemplate[]>('/prompts'),

  createPrompt: (input: {
    name: string
    category: string
    body: string
    description?: string
    variables?: string[]
  }) => request<PromptTemplate>('/prompts', { method: 'POST', body: JSON.stringify(input) }),

  // ---- 数据源 ----
  availableConnectors: () => request<AvailableConnector[]>('/connectors/available'),
  listConnectors: () => request<Connector[]>('/connectors'),
  createConnector: (key: string, config?: Record<string, unknown>) =>
    request<Connector>('/connectors', { method: 'POST', body: JSON.stringify({ key, config: config ?? {} }) }),
  deleteConnector: (id: string) => request<void>(`/connectors/${id}`, { method: 'DELETE' }),
  validateConnector: (id: string) =>
    request<{ ok: boolean; message: string }>(`/connectors/${id}/validate`, { method: 'POST' }),
  syncConnector: (id: string, window?: { start: string; end: string }) =>
    request<SyncStats>(`/connectors/${id}/sync`, {
      method: 'POST',
      body: JSON.stringify(window ? { window_start: window.start, window_end: window.end } : {}),
    }),
  listRuns: (id: string) => request<SyncRun[]>(`/connectors/${id}/runs`),
}
