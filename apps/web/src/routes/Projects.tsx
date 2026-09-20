import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { toast } from '../components/Toast'
import { Badge, Button, EmptyState, ErrorState, Spinner, cn } from '../components/ui'
import { useMaterialStats, useTopics } from '../hooks/useWorkspace'
import { api, type Assessment, type ProjectDetail } from '../lib/api'
import { todayISO } from '../lib/format'

const STATUS_LABEL: Record<string, string> = {
  collecting: '收集素材',
  reviewing: '检查中',
  ready: '就绪',
  composing: '写作中',
  drafting: '草稿',
  completed: '已完成',
  archived: '归档',
  cancelled: '已取消',
}

/**
 * 选题：从素材库挑一组素材 → 校验可写作性 → 触发写作。
 *
 * ★ 关键产品规则（docs/06 §1 R4）：点评**不是**前置条件。
 * 只有未处置的合规红线才会拦住写作。
 */
export function Projects() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [activeId, setActiveId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [draftTitle, setDraftTitle] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [pickerFilter, setPickerFilter] = useState({ date: todayISO(), minScore: 0, topic: '' })

  const topicsQuery = useTopics()
  const statsQuery = useMaterialStats(pickerFilter.date)
  const projectsQuery = useQuery({ queryKey: ['projects'], queryFn: () => api.listProjects() })
  const promptsQuery = useQuery({ queryKey: ['prompts'], queryFn: () => api.listPrompts() })
  const materialsQuery = useQuery({
    queryKey: ['materials', 'picker', pickerFilter],
    queryFn: () =>
      api.listMaterials({
        date: pickerFilter.date || undefined,
        min_score: pickerFilter.minScore || undefined,
        topic: pickerFilter.topic ? [pickerFilter.topic] : undefined,
        limit: 100,
      }),
  })

  const projects = projectsQuery.data ?? []
  useEffect(() => {
    if (!activeId && projects.length) setActiveId(projects[0].id)
  }, [projects, activeId])

  const detailQuery = useQuery({
    queryKey: ['project', activeId],
    queryFn: () => api.getProject(activeId as string),
    enabled: !!activeId,
  })
  const detail: ProjectDetail | undefined = detailQuery.data

  const createProject = useMutation({
    mutationFn: () =>
      api.createProject({
        title: draftTitle || '未命名选题',
        material_ids: picked,
        prompt_ids: (promptsQuery.data ?? []).filter((p) => p.category === 'taboo').map((p) => p.id),
      }),
    onSuccess: (p) => {
      toast(`选题已创建 · 含 ${p.materials.length} 条素材`)
      qc.invalidateQueries({ queryKey: ['projects'] })
      setCreating(false)
      setDraftTitle('')
      setPicked([])
      setActiveId(p.id)
    },
    onError: (e: Error) => toast(`创建失败：${e.message}`),
  })

  const addMaterials = useMutation({
    mutationFn: (ids: string[]) => api.addProjectMaterials(activeId as string, ids),
    onSuccess: (res) => {
      toast(`已加入 ${res.added ?? 0} 条素材`)
      qc.invalidateQueries({ queryKey: ['project', activeId] })
      qc.invalidateQueries({ queryKey: ['projects'] })
    },
    onError: (e: Error) => toast(`加入失败：${e.message}`),
  })

  const removeMaterial = useMutation({
    mutationFn: (materialId: string) => api.removeProjectMaterial(activeId as string, materialId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['project', activeId] })
      qc.invalidateQueries({ queryKey: ['projects'] })
    },
  })

  const compose = useMutation({
    mutationFn: () => api.composeProject(activeId as string),
    onSuccess: (res) => {
      toast(`已入队 · ${res.mode === 'digest' ? '素材综述模式' : '观点驱动模式'}`)
      navigate(`/projects/${activeId}/compose`)
    },
    onError: (e: Error) => toast(`无法写作：${e.message}`),
  })

  const assessment: Assessment | undefined = detail?.assessment
  const candidateMaterials = materialsQuery.data ?? []
  const materials = detail?.materials ?? []

  const promptsByCat = useMemo(() => {
    const g: Record<string, typeof promptsQuery.data> = {}
    for (const p of promptsQuery.data ?? []) (g[p.category] ??= []).push(p)
    return g
  }, [promptsQuery.data])

  return (
    <div className="grid h-full grid-cols-[280px_minmax(0,1fr)]">
      {/* 左：选题列表 */}
      <aside className="overflow-y-auto border-r border-slate-200 bg-white p-2">
        <div className="flex items-center justify-between px-1 pb-2">
          <span className="text-[11px] font-medium text-slate-500">我的选题</span>
          <Button size="sm" variant="ghost" onClick={() => setCreating((v) => !v)}>
            + 新建
          </Button>
        </div>

        {creating && (
          <div className="mb-2 rounded border border-indigo-200 bg-indigo-50/50 p-2">
            <input
              value={draftTitle}
              onChange={(e) => setDraftTitle(e.target.value)}
              placeholder="选题标题（可先空着）"
              className="mb-2 w-full rounded border border-slate-300 px-2 py-1 text-xs outline-none focus:border-indigo-500"
            />
            <div className="mb-1 text-[11px] text-slate-500">
              从素材库挑（已选 {picked.length} 条）
            </div>
            <div className="mb-1 flex gap-1">
              <select
                value={pickerFilter.date}
                onChange={(e) => setPickerFilter((f) => ({ ...f, date: e.target.value }))}
                className="h-6 flex-1 rounded border border-slate-300 bg-white text-[11px]"
              >
                {(statsQuery.data?.dates?.length ? statsQuery.data.dates : [todayISO()]).map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
              <select
                value={pickerFilter.minScore}
                onChange={(e) => setPickerFilter((f) => ({ ...f, minScore: Number(e.target.value) }))}
                className="h-6 rounded border border-slate-300 bg-white text-[11px]"
              >
                <option value={0}>全部</option>
                <option value={8}>≥8</option>
                <option value={6}>≥6</option>
              </select>
            </div>
            <select
              value={pickerFilter.topic}
              onChange={(e) => setPickerFilter((f) => ({ ...f, topic: e.target.value }))}
              className="mb-1 h-6 w-full rounded border border-slate-300 bg-white text-[11px]"
            >
              <option value="">全部主题</option>
              {(topicsQuery.data ?? []).map((t) => (
                <option key={t.id} value={t.name}>
                  {t.name}
                </option>
              ))}
            </select>

            <div className="max-h-40 space-y-1 overflow-y-auto">
              {candidateMaterials.map((m) => (
                <label key={m.id} className="flex cursor-pointer items-start gap-1.5 text-[11px]">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={picked.includes(m.id)}
                    onChange={() =>
                      setPicked((s) => (s.includes(m.id) ? s.filter((x) => x !== m.id) : [...s, m.id]))
                    }
                  />
                  <span className="flex-1">
                    <span className="rounded bg-indigo-600 px-1 text-[10px] font-semibold text-white">
                      {m.score}
                    </span>{' '}
                    <span className="line-clamp-2 text-slate-600">{m.news?.title}</span>
                    {m.annotation && <Badge className="ml-1 bg-emerald-50 text-emerald-700">已批注</Badge>}
                  </span>
                </label>
              ))}
              {!materialsQuery.isLoading && candidateMaterials.length === 0 && (
                <div className="text-[11px] text-slate-400">这个筛选下没有素材</div>
              )}
            </div>

            <div className="mt-2 flex gap-1">
              <Button
                size="sm"
                variant="primary"
                disabled={createProject.isPending}
                onClick={() => createProject.mutate()}
              >
                创建选题
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setCreating(false)}>
                取消
              </Button>
            </div>
            <div className="mt-1 text-[10px] text-slate-400">
              素材可以没有点评 —— 那样会走「素材综述模式」。
            </div>
          </div>
        )}

        {projectsQuery.isLoading && (
          <div className="flex items-center gap-2 p-2 text-xs text-slate-500">
            <Spinner /> 加载中…
          </div>
        )}
        <div className="space-y-1">
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => setActiveId(p.id)}
              className={cn(
                'w-full rounded-md border p-2 text-left transition-colors',
                p.id === activeId ? 'border-indigo-400 bg-indigo-50' : 'border-slate-200 hover:border-slate-300',
              )}
            >
              <div className="flex items-start justify-between gap-1">
                <span className="line-clamp-2 flex-1 text-xs font-medium text-slate-800">{p.title}</span>
                <Badge
                  className={
                    p.assessment?.with_blocker
                      ? 'bg-rose-50 text-rose-700'
                      : p.status === 'ready'
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-slate-100 text-slate-500'
                  }
                >
                  {p.assessment?.with_blocker ? '有红线' : STATUS_LABEL[p.status] ?? p.status}
                </Badge>
              </div>
              <div className="mt-1 text-[10px] text-slate-500">
                {p.assessment?.materials ?? 0} 条素材 · {p.assessment?.with_annotation ?? 0} 条带点评
              </div>
            </button>
          ))}
        </div>
      </aside>

      {/* 右：选题详情 */}
      <section className="overflow-y-auto p-4">
        {detailQuery.isLoading && (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> 加载中…
          </div>
        )}
        {detailQuery.error && <ErrorState message={(detailQuery.error as Error).message} />}
        {!detailQuery.isLoading && !detail && (
          <EmptyState title="还没有选题" hint="点左上「+ 新建」，从素材库挑一组素材即可。" />
        )}

        {detail && assessment && (
          <>
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <h2 className="text-base font-semibold text-slate-900">{detail.title}</h2>
              <Badge>{STATUS_LABEL[detail.status] ?? detail.status}</Badge>
              {detail.platform && <Badge>{detail.platform}</Badge>}
              {assessment.mode === 'digest' && (
                <Badge className="bg-amber-50 text-amber-700">素材综述模式</Badge>
              )}
            </div>

            {/* 可写作性 */}
            <div
              className={cn(
                'mb-4 rounded-lg border p-3',
                assessment.writable
                  ? 'border-emerald-200 bg-emerald-50'
                  : 'border-rose-200 bg-rose-50',
              )}
            >
              <div className="flex flex-wrap items-center gap-3">
                <div>
                  <div className="text-sm font-semibold text-slate-800">
                    {assessment.writable
                      ? assessment.mode === 'opinion'
                        ? `可以开始写作 · ${assessment.stats.with_annotation} 条带点评（观点驱动）`
                        : '可以开始写作 · 素材综述模式'
                      : '还不能写作'}
                  </div>
                  <div className="mt-0.5 text-[11px] text-slate-600">
                    素材 {assessment.stats.materials} 条 · 带点评 {assessment.stats.with_annotation} 条 ·
                    纯素材 {assessment.stats.without_annotation} 条
                    {assessment.stats.with_blocker > 0 && ` · 含红线 ${assessment.stats.with_blocker} 条`}
                  </div>
                </div>
                <div className="ml-auto">
                  <Button
                    size="md"
                    variant="primary"
                    disabled={!assessment.writable || compose.isPending}
                    onClick={() => compose.mutate()}
                  >
                    {compose.isPending ? '提交中…' : '🚀 开始写作'}
                  </Button>
                </div>
              </div>
              {assessment.blocking_reasons.length > 0 && (
                <ul className="mt-2 list-disc pl-4 text-[11px] text-rose-700">
                  {assessment.blocking_reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              )}
              {assessment.writable && assessment.mode === 'digest' && (
                <div className="mt-2 text-[11px] text-amber-700">
                  ★ 这组素材还没有点评：产出会有事实、有结构，但缺你的判断。建议至少给 1~2 条素材写一句。
                </div>
              )}
            </div>

            {/* 素材 */}
            <div className="mb-4 rounded-lg border border-slate-200 bg-white">
              <div className="flex items-center gap-2 border-b border-slate-100 px-3 py-2">
                <span className="text-xs font-semibold text-slate-700">素材 · {materials.length} 条</span>
                <span className="text-[11px] text-slate-400">选题的唯一原料</span>
                <div className="ml-auto">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => addMaterials.mutate(picked)}
                    disabled={!picked.length || addMaterials.isPending}
                  >
                    加入已勾选（{picked.length}）
                  </Button>
                </div>
              </div>
              <div className="divide-y divide-slate-100">
                {materials.length === 0 && (
                  <div className="p-3 text-[11px] text-slate-400">
                    还没有素材。在左侧新建时勾选，或到资讯中心标记。
                  </div>
                )}
                {materials.map((m) => (
                  <div key={m.id} className="flex items-start gap-2 p-3">
                    <span className="rounded bg-indigo-600 px-1.5 text-[11px] font-semibold text-white">
                      {m.score}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-xs font-medium text-slate-800">{m.news?.title}</div>
                      <div className="mt-0.5 text-[10px] text-slate-500">
                        {m.news?.source_name} · {m.material_date}
                        {m.topics.length ? ` · ${m.topics.join('/')}` : ''}
                      </div>
                      {m.annotation ? (
                        <div className="mt-1 line-clamp-2 text-[11px] text-slate-500">{m.annotation.body}</div>
                      ) : (
                        <div className="mt-1 text-[11px] text-slate-400">
                          无点评 · 将作为背景素材参与写作
                        </div>
                      )}
                    </div>
                    {m.has_blocker ? (
                      <Badge className="bg-rose-50 text-rose-700">有红线</Badge>
                    ) : m.annotation ? (
                      <Badge className="bg-emerald-50 text-emerald-700">已批注</Badge>
                    ) : (
                      <Badge className="bg-slate-100 text-slate-400">未批注</Badge>
                    )}
                    <button
                      onClick={() => removeMaterial.mutate(m.id)}
                      className="rounded p-1 text-slate-300 hover:bg-slate-100 hover:text-rose-600"
                      title="移出选题"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            </div>

            {/* 提示词组合 */}
            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <div className="mb-2 text-xs font-semibold text-slate-700">提示词组合</div>
              <div className="flex flex-wrap gap-1.5">
                {(detail.prompts.length ? detail.prompts : (promptsQuery.data ?? []).slice(0, 4)).map((p) => (
                  <Badge key={p.id} className="bg-indigo-50 text-indigo-700">
                    {p.name} v{p.version_no}
                  </Badge>
                ))}
              </div>
              <div className="mt-2 text-[11px] text-slate-500">
                {Object.entries(promptsByCat)
                  .map(([cat, list]) => `${cat} ${list?.length ?? 0}`)
                  .join(' · ')}
                （人格 + 结构 + 禁忌，可叠加）
              </div>
              <Link to="/prompts" className="mt-2 inline-block text-[11px] text-indigo-600 hover:underline">
                管理提示词 →
              </Link>
            </div>
          </>
        )}
      </section>
    </div>
  )
}
