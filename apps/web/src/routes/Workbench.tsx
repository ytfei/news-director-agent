import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnnotationBox } from '../components/AnnotationBox'
import { Badge, Button, EmptyState, ErrorState, Spinner, cn } from '../components/ui'
import { useMaterialStats, useTopics } from '../hooks/useWorkspace'
import { api, type Material } from '../lib/api'
import { contentTypeLabel, formatTime, todayISO } from '../lib/format'

const VERDICT_BADGE: Record<string, { text: string; cls: string }> = {
  passed: { text: '通过', cls: 'bg-emerald-50 text-emerald-700' },
  needs_revision: { text: '需修改', cls: 'bg-amber-50 text-amber-700' },
  blocked: { text: '有红线', cls: 'bg-rose-50 text-rose-700' },
}

/**
 * 点评工作台：**数据源是素材库**（docs/06 §1 R1）。
 *
 * 这里刻意不做二次资讯筛选 —— 用户在资讯中心已经给过评分与主题，
 * 工作台只按「日期 / 评分 / 主题 / 有无批注」取用。
 */
export function Workbench() {
  const navigate = useNavigate()
  const [date, setDate] = useState(todayISO())
  const [minScore, setMinScore] = useState(0)
  const [topicFilter, setTopicFilter] = useState<string[]>([])
  const [onlyTodo, setOnlyTodo] = useState(false)
  const [activeId, setActiveId] = useState<string | null>(null)

  const topicsQuery = useTopics()
  const statsQuery = useMaterialStats(date)

  const preselect: string[] = useMemo(() => {
    try {
      return JSON.parse(sessionStorage.getItem('workbench:preselect') ?? '[]') as string[]
    } catch {
      return []
    }
  }, [])

  const materialsQuery = useQuery({
    queryKey: ['materials', 'workbench', { date, minScore, topicFilter, onlyTodo }],
    queryFn: () =>
      api.listMaterials({
        date,
        min_score: minScore || undefined,
        topic: topicFilter.length ? topicFilter : undefined,
        has_annotation: onlyTodo ? false : undefined,
        limit: 200,
      }),
  })

  const materials: Material[] = materialsQuery.data ?? []

  useEffect(() => {
    if (activeId) return
    if (preselect.length) {
      const hit = materials.find((m) => preselect.includes(m.id))
      if (hit) setActiveId(hit.id)
    } else if (materials.length) {
      setActiveId(materials[0].id)
    }
  }, [materials, preselect, activeId])

  const active = materials.find((m) => m.id === activeId) ?? null
  const withAnnotation = materials.filter((m) => m.annotation)

  const factCardQuery = useQuery({
    queryKey: ['fact-card', active?.news_id],
    queryFn: () => api.getFactCard(active!.news_id),
    enabled: !!active,
    retry: false,
  })

  return (
    <div className="flex h-full flex-col">
      {/* 素材筛选条 */}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-white px-4 py-2">
        <span className="text-xs font-medium text-slate-700">素材库</span>
        <span className="text-[11px] text-slate-400">工作台只处理素材，不直接处理资讯</span>
        <select
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="h-7 rounded border border-slate-300 bg-white px-2 text-xs"
        >
          {(statsQuery.data?.dates?.length ? statsQuery.data.dates : [todayISO()]).map((d) => (
            <option key={d} value={d}>
              {d}
              {d === todayISO() ? '（今天）' : ''}
            </option>
          ))}
        </select>
        <select
          value={minScore}
          onChange={(e) => setMinScore(Number(e.target.value))}
          className="h-7 rounded border border-slate-300 bg-white px-2 text-xs"
        >
          <option value={0}>全部评分</option>
          <option value={8}>≥ 8</option>
          <option value={6}>≥ 6</option>
        </select>
        <div className="flex flex-wrap gap-1">
          {(topicsQuery.data ?? []).slice(0, 10).map((t) => (
            <button
              key={t.id}
              onClick={() =>
                setTopicFilter((s) =>
                  s.includes(t.name) ? s.filter((x) => x !== t.name) : [...s, t.name],
                )
              }
              className={cn(
                'rounded-full border px-2 py-0.5 text-[11px]',
                topicFilter.includes(t.name)
                  ? 'border-indigo-400 bg-indigo-50 font-medium text-indigo-700'
                  : 'border-slate-300 bg-white text-slate-600',
              )}
            >
              {t.name}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1 text-[11px] text-slate-500">
          <input type="checkbox" checked={onlyTodo} onChange={(e) => setOnlyTodo(e.target.checked)} />
          只看未批注
        </label>
        <span className="ml-auto text-[11px] text-slate-500">
          筛出 <b>{materials.length}</b> 条素材 · 其中 <b>{withAnnotation.length}</b> 条已批注
        </span>
        <Button
          size="sm"
          variant="outline"
          disabled={!withAnnotation.length}
          onClick={() => {
            api
              .checkAnnotations(withAnnotation.map((m) => m.id))
              .then((res) => {
                const s = res.verdict_summary
                const first = res.reports[0]?.id
                if (first) navigate(`/reviews/${first}`)
                alert(
                  `检查完成：通过 ${s.passed ?? 0} / 需修改 ${s.needs_revision ?? 0} / 红线 ${s.blocked ?? 0}`,
                )
              })
              .catch((e: Error) => alert(`检查失败：${e.message}`))
          }}
        >
          🛡️ 全量提交检查（{withAnnotation.length}）
        </Button>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[240px_minmax(0,1fr)_280px]">
        {/* 左：素材列表 */}
        <div className="overflow-y-auto border-r border-slate-200 bg-white p-2">
          {materialsQuery.isLoading && (
            <div className="flex items-center gap-2 p-3 text-xs text-slate-500">
              <Spinner /> 加载中…
            </div>
          )}
          {materialsQuery.error && <ErrorState message={(materialsQuery.error as Error).message} />}
          {!materialsQuery.isLoading && materials.length === 0 && (
            <div className="p-3 text-xs text-slate-400">
              这个筛选下还没有素材，去资讯中心「加入素材」。
            </div>
          )}
          <div className="space-y-1">
            {materials.map((m) => {
              const verdict = m.annotation?.verdict
              const vb = verdict ? VERDICT_BADGE[verdict] : null
              return (
                <button
                  key={m.id}
                  onClick={() => setActiveId(m.id)}
                  className={cn(
                    'w-full rounded-md border p-2 text-left transition-colors',
                    m.id === activeId
                      ? 'border-indigo-400 bg-indigo-50'
                      : 'border-slate-200 hover:border-slate-300',
                  )}
                >
                  <div className="flex items-start gap-2">
                    <span className="rounded bg-indigo-600 px-1.5 text-[11px] font-semibold text-white">
                      {m.score}
                    </span>
                    <span className="line-clamp-2 flex-1 text-xs font-medium text-slate-800">
                      {m.news?.title}
                    </span>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1 text-[10px] text-slate-500">
                    {m.topics.map((t) => (
                      <Badge key={t} className="bg-slate-100 text-slate-600">
                        {t}
                      </Badge>
                    ))}
                    <span>{m.material_date}</span>
                  </div>
                  <div className="mt-1">
                    {vb ? (
                      <Badge className={vb.cls}>{vb.text}</Badge>
                    ) : (
                      <Badge className="bg-slate-100 text-slate-400">未批注</Badge>
                    )}
                    {m.annotation && m.annotation.open_findings > 0 && (
                      <Badge className="ml-1 bg-amber-50 text-amber-700">
                        待处理 {m.annotation.open_findings}
                      </Badge>
                    )}
                  </div>
                </button>
              )
            })}
          </div>
        </div>

        {/* 中：编辑器 */}
        <div className="min-w-0 overflow-y-auto p-4">
          {!active && !materialsQuery.isLoading && (
            <EmptyState
              title="左侧选一条素材开始批注"
              hint="没有批注的素材也能直接进选题，AI 会按素材综述来写。"
            />
          )}
          {active && (
            <>
              <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
                <span className="font-medium text-slate-700">{active.news?.source_name}</span>
                <span>·</span>
                <span>{active.news ? formatTime(active.news.published_at) : ''}</span>
                {active.news && <Badge>{contentTypeLabel(active.news.content_type)}</Badge>}
                <Badge className="bg-indigo-600 text-white">素材 {active.score}/10</Badge>
                {active.topics.map((t) => (
                  <Badge key={t}>{t}</Badge>
                ))}
              </div>
              <h2 className="mb-3 text-[15px] font-semibold leading-6 text-slate-900">
                {active.news?.title}
              </h2>

              <AnnotationBox
                materialId={active.id}
                initialBody={active.annotation?.body ?? ''}
                versionNo={active.annotation?.version_no ?? 0}
                status={active.annotation?.status}
                verdict={active.annotation?.verdict ?? null}
                onClose={() => setActiveId(null)}
                onJumpReview={() => navigate('/reviews')}
              />

              <div className="mt-4 rounded-lg border border-slate-200 bg-white p-3 text-[11px] leading-5 text-slate-500">
                <b className="text-slate-700">批注是可选的加深</b>
                ：写了点评 → 观点驱动的稿子；没写 → 素材综述。需要事实核查时，
                fact 轨道会用这条资讯的事实基线（FactCard）来比对。
              </div>
            </>
          )}
        </div>

        {/* 右：素材原文 + 事实基线 */}
        <div className="overflow-y-auto border-l border-slate-200 bg-white p-3">
          {active?.news && (
            <>
              <div className="mb-2 text-[11px] font-semibold text-slate-700">素材原文</div>
              <p className="text-[12px] leading-6 text-slate-600">{active.news.summary}</p>
              {active.news.url && (
                <a
                  href={active.news.url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 inline-block text-[11px] text-indigo-600 hover:underline"
                >
                  原文 ↗
                </a>
              )}

              <div className="mt-4 border-t border-slate-100 pt-3">
                <div className="mb-2 text-[11px] font-semibold text-slate-700">
                  事实基线 · FactCard
                </div>
                {factCardQuery.isLoading && <div className="text-[11px] text-slate-400">加载中…</div>}
                {factCardQuery.isError && (
                  <div className="rounded border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-700">
                    尚未生成。没有事实基线时，fact 轨道会退化为「无法验证」，不会凭空报错。
                  </div>
                )}
                {factCardQuery.data && (
                  <>
                    <div className="space-y-2">
                      {factCardQuery.data.claims.slice(0, 6).map((c) => (
                        <div key={c.id} className="flex items-start gap-1.5">
                          <Badge
                            className={
                              c.status === 'verified'
                                ? 'bg-emerald-50 text-emerald-700'
                                : c.status === 'contradicted'
                                  ? 'bg-rose-50 text-rose-700'
                                  : 'bg-slate-100 text-slate-500'
                            }
                          >
                            {c.status === 'verified'
                              ? '已验证'
                              : c.status === 'contradicted'
                                ? '有冲突'
                                : c.status === 'outdated'
                                  ? '已过时'
                                  : '无法验证'}
                          </Badge>
                          <span className="flex-1 text-[11px] leading-5 text-slate-600">{c.claim}</span>
                        </div>
                      ))}
                    </div>
                    {factCardQuery.data.open_questions.length > 0 && (
                      <div className="mt-3 rounded border border-slate-200 p-2">
                        <div className="mb-1 text-[11px] font-medium text-slate-600">还没查清</div>
                        <ul className="list-disc space-y-0.5 pl-4 text-[11px] text-slate-500">
                          {factCardQuery.data.open_questions.map((q) => (
                            <li key={q}>{q}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
