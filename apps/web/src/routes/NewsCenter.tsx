import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AnnotationBox } from '../components/AnnotationBox'
import { FilterBar, rangeToSince, type Filters } from '../components/FilterBar'
import { MaterialSheet } from '../components/MaterialSheet'
import { NewsCard } from '../components/NewsCard'
import { NewsDetailDrawer } from '../components/NewsDetailDrawer'
import { toast } from '../components/Toast'
import { Badge, Button, EmptyState, ErrorState, Spinner, cn } from '../components/ui'
import { useKeyboardNav } from '../hooks/useKeyboardNav'
import { useNewsActions } from '../hooks/useNewsActions'
import {
  useDeleteMaterial,
  useMarkMaterial,
  useMaterialStats,
  useTopics,
} from '../hooks/useWorkspace'
import {
  api,
  type AnnotationBrief,
  type MaterialBadge,
  type NewsItem,
} from '../lib/api'
import { todayISO } from '../lib/format'

const PAGE_SIZE = 50
type View = 'all' | 'material' | 'todo'

interface Row {
  news: NewsItem
  material: MaterialBadge | null
  /** 素材主键：批注挂在素材上，没有它就不能批注 */
  materialId: string | null
  annotation: AnnotationBrief | null
}

const TABS: { key: View; label: string }[] = [
  { key: 'all', label: '全部资讯' },
  { key: 'material', label: '我的素材' },
  { key: 'todo', label: '待批注' },
]

/**
 * 资讯中心 —— 全站唯一的「筛选 + 批注 + 标记素材」入口（docs/06 §1 R2/R3）。
 *
 * 三种视图共用一套卡片：
 * - all      全量资讯（时间范围 / 类型 / 行业）
 * - material 素材库（日期 / 评分 / 主题）
 * - todo     只看还没批注的素材
 */
export function NewsCenter() {
  const [params, setParams] = useSearchParams()
  const view = (params.get('view') as View) || 'all'

  const [filters, setFilters] = useState<Filters>({ range: '3d', content_type: '', industry: '' })
  const [date, setDate] = useState(todayISO())
  const [minScore, setMinScore] = useState(0)
  const [topicFilter, setTopicFilter] = useState<string[]>([])

  const [matOpen, setMatOpen] = useState<string | null>(null)
  const [annOpen, setAnnOpen] = useState<{ newsId: string; materialId: string } | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [cursor, setCursor] = useState(0)

  const topicsQuery = useTopics()
  const statsQuery = useMaterialStats(date)
  const mark = useMarkMaterial()
  const removeMaterial = useDeleteMaterial()
  const { starred, toggleStar, toast: actionToast, clearToast } = useNewsActions()

  const listQuery = useInfiniteQuery({
    queryKey: ['news', 'center', filters],
    initialPageParam: 0,
    enabled: view === 'all',
    queryFn: ({ pageParam }) =>
      api.listNews({
        content_type: filters.content_type || undefined,
        industry: filters.industry || undefined,
        since: rangeToSince(filters.range),
        limit: PAGE_SIZE,
        offset: pageParam,
      }),
    getNextPageParam: (last, _all, lastParam) =>
      last.length === PAGE_SIZE ? (lastParam as number) + PAGE_SIZE : undefined,
  })

  const materialQuery = useQuery({
    queryKey: ['materials', { view, date, minScore, topicFilter }],
    enabled: view !== 'all',
    queryFn: () =>
      api.listMaterials({
        // 日期即「素材组」：默认看当天，与侧栏统计口径一致
        date,
        min_score: minScore || undefined,
        topic: topicFilter.length ? topicFilter : undefined,
        has_annotation: view === 'todo' ? false : undefined,
        limit: 100,
      }),
  })

  const rows: Row[] = useMemo(() => {
    if (view === 'all') {
      return (listQuery.data?.pages ?? []).flat().map((n) => ({
        news: n,
        material: n.material,
        materialId: n.material?.id ?? null,
        annotation: n.annotation,
      }))
    }
    return (materialQuery.data ?? [])
      .filter((m) => m.news)
      .map((m) => ({
        news: m.news as NewsItem,
        material: { id: m.id, score: m.score, topics: m.topics, material_date: m.material_date },
        materialId: m.id,
        annotation: m.annotation,
      }))
  }, [view, listQuery.data, materialQuery.data])

  useEffect(() => setCursor(0), [filters, view, date, minScore, topicFilter])

  const current = rows[cursor]
  useKeyboardNav({
    count: rows.length,
    cursor,
    setCursor,
    enabled: view === 'all' && !openId && !matOpen && !annOpen,
    onStar: () => current && toggleStar(current.news),
    onRate: () => undefined,
    onToggleSelect: () => current && toggleSelect(current.news.id),
  })

  const listRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    listRef.current?.querySelector(`[data-index="${cursor}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [cursor])

  const sentinel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = sentinel.current
    if (!el || view !== 'all') return
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && listQuery.hasNextPage && !listQuery.isFetchingNextPage) {
          listQuery.fetchNextPage()
        }
      },
      { rootMargin: '400px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [listQuery, view])

  const toggleSelect = (id: string) =>
    setSelected((s) => {
      const n = new Set(s)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })

  /** 批注必须挂在素材上：没有素材时静默建一个（评分默认 5），再打开批注框 */
  const openAnnotate = (row: Row) => {
    if (row.materialId) {
      setAnnOpen({ newsId: row.news.id, materialId: row.materialId })
      setMatOpen(null)
      return
    }
    mark.mutate(
      { news_id: row.news.id, score: 5, material_date: date },
      {
        onSuccess: (res) => {
          toast('已自动加入素材，可直接批注')
          setAnnOpen({ newsId: row.news.id, materialId: res.material.id })
        },
      },
    )
  }

  const batchMark = async (score: number, topic: string) => {
    const targets = rows.filter((r) => selected.has(r.news.id))
    const topics = topic.trim() ? [topic.trim()] : []
    await Promise.all(
      targets.map((r) =>
        api.markMaterial({ news_id: r.news.id, score, topics, material_date: date }),
      ),
    )
    toast(`${targets.length} 条已加入素材 · 评分 ${score}${topics.length ? ` · ${topics[0]}` : ''}`)
    setSelected(new Set())
    listQuery.refetch()
    materialQuery.refetch()
    statsQuery.refetch()
  }

  const loading = view === 'all' ? listQuery.isLoading : materialQuery.isLoading
  const error = view === 'all' ? listQuery.error : materialQuery.error
  const stats = statsQuery.data

  return (
    <div className="flex h-full">
      <div className="flex min-w-0 flex-1 flex-col">
        {/* 视图切换 */}
        <div className="flex items-center gap-2 border-b border-slate-200 bg-white px-4 py-2">
          <div className="flex overflow-hidden rounded-md border border-slate-300">
            {TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => {
                  setParams(t.key === 'all' ? {} : { view: t.key })
                  setSelected(new Set())
                }}
                className={cn(
                  'px-3 py-1 text-xs transition-colors',
                  view === t.key ? 'bg-indigo-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-50',
                )}
              >
                {t.label}
                {t.key === 'material' && stats ? ` ${stats.total}` : ''}
                {t.key === 'todo' && stats ? ` ${stats.without_annotation}` : ''}
              </button>
            ))}
          </div>
          <span className="text-[11px] text-slate-400">
            筛选与批注都在这一页完成，不跳页
          </span>
        </div>

        {view === 'all' ? (
          <FilterBar
            value={filters}
            onChange={setFilters}
            resultCount={rows.length}
            loading={loading}
          />
        ) : (
          <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-indigo-50/50 px-4 py-2">
            <span className="text-[11px] font-medium text-slate-600">素材筛选</span>
            <select
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="h-7 rounded border border-slate-300 bg-white px-2 text-xs"
            >
              {(stats?.dates?.length ? stats.dates : [todayISO()]).map((d) => (
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
              <option value={8}>≥ 8（最想写）</option>
              <option value={6}>≥ 6</option>
              <option value={4}>≥ 4</option>
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
                      ? 'border-indigo-400 bg-white font-medium text-indigo-700'
                      : 'border-slate-300 bg-white text-slate-600',
                  )}
                >
                  {t.name}
                </button>
              ))}
            </div>
            {(minScore > 0 || topicFilter.length > 0) && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setMinScore(0)
                  setTopicFilter([])
                }}
              >
                清空
              </Button>
            )}
            <span className="ml-auto text-[11px] text-slate-500">{rows.length} 条素材</span>
          </div>
        )}

        {view === 'all' && (
          <div className="flex items-center gap-2 border-b border-slate-100 bg-white px-4 py-1.5 text-[11px] text-slate-400">
            <span className="kbd">j</span>/<span className="kbd">k</span> 移动
            <span className="kbd">s</span> 收藏
            <span className="kbd">space</span> 选中
            <Badge className="bg-indigo-50 text-indigo-600">🔖 加入素材 → 评分 / 主题 / 日期</Badge>
          </div>
        )}

        <div ref={listRef} className="flex-1 overflow-y-auto p-4">
          {loading && (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Spinner /> 加载中…
            </div>
          )}
          {error && <ErrorState message={(error as Error).message} />}
          {!loading && !error && rows.length === 0 && (
            <EmptyState
              title={view === 'todo' ? '所有素材都批注完了' : '这里还没有内容'}
              hint={
                view === 'material'
                  ? '在「全部资讯」里点「加入素材」，标的资讯会按日期归组到这里。'
                  : '放宽时间范围，或到「数据源」页手动触发一次同步。'
              }
            />
          )}

          <div className="space-y-2">
            {rows.map((row, i) => (
              <div key={row.news.id} data-index={i}>
                <NewsCard
                  item={row.news}
                  material={row.material}
                  annotation={row.annotation}
                  active={i === cursor}
                  selected={selected.has(row.news.id)}
                  starred={starred.has(row.news.id)}
                  onOpen={(n) => setOpenId(n.id)}
                  onToggleSelect={toggleSelect}
                  onStar={(n) => toggleStar(n)}
                  onMarkMaterial={() => {
                    setMatOpen(matOpen === row.news.id ? null : row.news.id)
                    setAnnOpen(null)
                  }}
                  onAnnotate={() => openAnnotate(row)}
                  onRemoveMaterial={
                    row.materialId
                      ? () => removeMaterial.mutate(row.materialId as string)
                      : undefined
                  }
                />

                {matOpen === row.news.id && (
                  <MaterialSheet
                    newsId={row.news.id}
                    material={row.material}
                    topics={topicsQuery.data ?? []}
                    onClose={() => setMatOpen(null)}
                  />
                )}

                {annOpen?.newsId === row.news.id && (
                  <AnnotationBox
                    materialId={annOpen.materialId}
                    initialBody={row.annotation?.body ?? ''}
                    versionNo={row.annotation?.version_no ?? 0}
                    status={row.annotation?.status}
                    verdict={row.annotation?.verdict ?? null}
                    onClose={() => setAnnOpen(null)}
                    onJumpReview={() => {
                      setAnnOpen(null)
                      window.location.href = '/reviews'
                    }}
                  />
                )}
              </div>
            ))}
          </div>

          <div ref={sentinel} className="h-6" />
          {view === 'all' && listQuery.isFetchingNextPage && (
            <div className="flex items-center gap-2 py-3 text-xs text-slate-500">
              <Spinner /> 加载更多…
            </div>
          )}
        </div>

        {selected.size > 0 && (
          <BatchDock
            count={selected.size}
            onClear={() => setSelected(new Set())}
            onSubmit={batchMark}
            onGoWorkbench={() => {
              const ids = rows
                .filter((r) => selected.has(r.news.id))
                .map((r) => r.materialId)
                .filter(Boolean) as string[]
              sessionStorage.setItem('workbench:preselect', JSON.stringify(ids))
              window.location.href = '/workbench'
            }}
          />
        )}
      </div>

      {/* 侧栏：今日素材概览 */}
      <aside className="hidden w-64 shrink-0 overflow-y-auto border-l border-slate-200 bg-white p-3 xl:block">
        <div className="rounded-lg border border-slate-200 p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-700">素材概览</span>
            <span className="text-[11px] text-slate-400">{date}</span>
          </div>
          {stats ? (
            <>
              <Row2 label="条数" value={stats.total} />
              <Row2 label="已批注" value={stats.with_annotation} />
              <Row2 label="待批注" value={stats.without_annotation} />
              <Row2 label="平均评分" value={stats.avg_score} />
              <div className="mt-2 border-t border-slate-100 pt-2">
                <div className="mb-1 text-[11px] text-slate-400">按评分</div>
                <Bar label="≥8" n={stats.score_buckets.ge8} total={stats.total} />
                <Bar label="6~7" n={stats.score_buckets['6_7']} total={stats.total} />
                <Bar label="≤5" n={stats.score_buckets.le5} total={stats.total} />
              </div>
              {Object.keys(stats.by_topic).length > 0 && (
                <div className="mt-2 border-t border-slate-100 pt-2">
                  <div className="mb-1 text-[11px] text-slate-400">按主题</div>
                  <div className="flex flex-wrap gap-1">
                    {Object.entries(stats.by_topic).map(([t, n]) => (
                      <button
                        key={t}
                        onClick={() => {
                          setParams({ view: 'material' })
                          setTopicFilter([t])
                        }}
                        className="rounded-full border border-slate-300 px-2 py-0.5 text-[11px] text-slate-600 hover:border-indigo-400 hover:text-indigo-700"
                      >
                        {t} {n}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="text-[11px] text-slate-400">加载中…</div>
          )}
        </div>

        <div className="mt-3 rounded-lg border border-slate-200 p-3 text-[11px] leading-5 text-slate-500">
          <div className="mb-1 font-medium text-slate-700">为什么要标记素材</div>
          素材是点评与选题的唯一原料。标记时只做三件事：给分（多想写）、打主题（多维标签）、归入当天。
          没写点评的素材也能直接拿去写作，只是产出会偏综述。
        </div>

        <div className="mt-3 space-y-1.5">
          <Link
            to="/workbench"
            className="block rounded-md border border-slate-200 px-3 py-2 text-xs text-slate-600 hover:border-indigo-300 hover:text-indigo-700"
          >
            ✍️ 去点评工作台（按日期/评分/主题筛）
          </Link>
          <Link
            to="/projects"
            className="block rounded-md border border-slate-200 px-3 py-2 text-xs text-slate-600 hover:border-indigo-300 hover:text-indigo-700"
          >
            📁 用素材建选题
          </Link>
        </div>
      </aside>

      <NewsDetailDrawer item={rows.find((r) => r.news.id === openId)?.news ?? null} onClose={() => setOpenId(null)} />

      {actionToast && (
        <div
          onClick={clearToast}
          className="fixed bottom-6 left-1/2 z-40 -translate-x-1/2 rounded-full bg-slate-900 px-4 py-2 text-xs text-white shadow-lg"
        >
          {actionToast}
        </div>
      )}
    </div>
  )
}

function Row2({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between py-0.5 text-xs">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium text-slate-800">{value}</span>
    </div>
  )
}

function Bar({ label, n, total }: { label: string; n: number; total: number }) {
  const pct = total ? Math.round((n / total) * 100) : 0
  return (
    <div className="mb-1 flex items-center gap-2">
      <span className="w-8 text-[11px] text-slate-500">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full bg-indigo-500" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-4 text-right text-[11px] text-slate-500">{n}</span>
    </div>
  )
}

/** 批量操作浮层：批量加入素材（最常用的批量动作） */
function BatchDock({
  count,
  onClear,
  onSubmit,
  onGoWorkbench,
}: {
  count: number
  onClear: () => void
  onSubmit: (score: number, topic: string) => void
  onGoWorkbench: () => void
}) {
  const [score, setScore] = useState(7)
  const [topic, setTopic] = useState('')

  return (
    <div className="border-t border-slate-200 bg-white px-4 py-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-slate-600">
          已选中 <b>{count}</b> 条
        </span>
        <span className="text-[11px] text-slate-400">批量加入素材：</span>
        <select
          value={score}
          onChange={(e) => setScore(Number(e.target.value))}
          className="h-7 rounded border border-slate-300 bg-white px-2 text-xs"
        >
          {[10, 9, 8, 7, 6, 5, 4, 3, 2, 1].map((n) => (
            <option key={n} value={n}>
              评分 {n}
            </option>
          ))}
        </select>
        <input
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="主题（可空）"
          className="h-7 w-32 rounded border border-slate-300 px-2 text-xs outline-none focus:border-indigo-500"
        />
        <Button size="sm" variant="primary" onClick={() => onSubmit(score, topic)}>
          🔖 加入素材
        </Button>
        <Button size="sm" variant="outline" onClick={onGoWorkbench}>
          ✍️ 去工作台批量批注
        </Button>
        <div className="ml-auto">
          <Button size="sm" variant="ghost" onClick={onClear}>
            清空
          </Button>
        </div>
      </div>
    </div>
  )
}
