import { useInfiniteQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { NewsCard } from '../components/NewsCard'
import { NewsDetailDrawer } from '../components/NewsDetailDrawer'
import { FilterBar, rangeToSince, type Filters } from '../components/FilterBar'
import { Badge, EmptyState, ErrorState, Spinner } from '../components/ui'
import { useKeyboardNav } from '../hooks/useKeyboardNav'
import { useNewsActions } from '../hooks/useNewsActions'
import { api } from '../lib/api'

const PAGE_SIZE = 50

/**
 * 资讯流。mode=inbox 时只取今日并按重要度排序（兴趣召回端点待 M2）。
 */
export function NewsFeed({ mode }: { mode: 'inbox' | 'feed' }) {
  const [filters, setFilters] = useState<Filters>({
    range: mode === 'inbox' ? 'today' : 'all',
    content_type: '',
    industry: '',
  })
  const [cursor, setCursor] = useState(0)
  const [openId, setOpenId] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const { starred, ratings, toggleStar, rate, toast, clearToast } = useNewsActions()

  const query = useInfiniteQuery({
    queryKey: ['news', mode, filters],
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      api.listNews({
        content_type: filters.content_type || undefined,
        industry: filters.industry || undefined,
        since: rangeToSince(filters.range),
        limit: PAGE_SIZE,
        offset: pageParam,
      }),
    getNextPageParam: (last, _all, lastParam) =>
      last.length === PAGE_SIZE ? lastParam + PAGE_SIZE : undefined,
  })

  const items = useMemo(() => {
    const all = (query.data?.pages ?? []).flat()
    if (mode !== 'inbox') return all
    return [...all].sort((a, b) => (b.importance ?? 0) - (a.importance ?? 0))
  }, [query.data, mode])

  // 筛选变化后重置游标
  useEffect(() => setCursor(0), [filters, mode])

  const current = items[cursor]
  useKeyboardNav({
    count: items.length,
    cursor,
    setCursor,
    enabled: !openId,
    onStar: () => current && toggleStar(current),
    onRate: (n) => current && rate(current, n),
    onToggleSelect: () =>
      current &&
      setSelected((s) => {
        const n = new Set(s)
        n.has(current.id) ? n.delete(current.id) : n.add(current.id)
        return n
      }),
  })

  // 光标跟随滚动
  const listRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-index="${cursor}"]`)
    el?.scrollIntoView({ block: 'nearest' })
  }, [cursor])

  const sentinel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = sentinel.current
    if (!el) return
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && query.hasNextPage && !query.isFetchingNextPage) {
          query.fetchNextPage()
        }
      },
      { rootMargin: '400px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [query])

  const toggleSelect = (id: string) =>
    setSelected((s) => {
      const n = new Set(s)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })

  return (
    <div className="flex h-full flex-col">
      <FilterBar
        value={filters}
        onChange={setFilters}
        resultCount={items.length}
        loading={query.isLoading}
      />

      {/* 快捷键提示 */}
      <div className="flex items-center gap-2 border-b border-slate-100 bg-white px-4 py-1.5 text-[11px] text-slate-400">
        <span className="kbd">j</span>/<span className="kbd">k</span> 移动
        <span className="kbd">s</span> 收藏
        <span className="kbd">1</span>–<span className="kbd">5</span> 评级
        <span className="kbd">space</span> 选中
        {mode === 'inbox' && <Badge className="bg-indigo-50 text-indigo-600">按重要度排序</Badge>}
      </div>

      <div ref={listRef} className="flex-1 overflow-y-auto p-4">
        {query.isLoading && (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> 加载中…
          </div>
        )}
        {query.error && <ErrorState message={(query.error as Error).message} />}
        {query.isSuccess && items.length === 0 && (
          <EmptyState
            title="这个条件下还没有资讯"
            hint="试着放宽时间范围，或到「数据源」页手动触发一次同步。"
          />
        )}

        <div className="space-y-2">
          {items.map((item, i) => (
            <div key={item.id} data-index={i}>
              <NewsCard
                item={item}
                active={i === cursor}
                selected={selected.has(item.id)}
                starred={starred.has(item.id)}
                onOpen={(it) => setOpenId(it.id)}
                onToggleSelect={toggleSelect}
                onStar={toggleStar}
              />
              {ratings[item.id] && (
                <div className="mt-1 pl-8 text-[11px] text-amber-600">
                  已评级 {ratings[item.id]}★
                </div>
              )}
            </div>
          ))}
        </div>

        <div ref={sentinel} className="h-6" />
        {query.isFetchingNextPage && (
          <div className="flex items-center gap-2 py-3 text-xs text-slate-500">
            <Spinner /> 加载更多…
          </div>
        )}
      </div>

      {/* 批量选中浮层：M2 才接点评，当前仅展示计数 */}
      {selected.size > 0 && (
        <div className="border-t border-slate-200 bg-white px-4 py-2.5">
          <div className="mx-auto flex max-w-3xl items-center justify-between">
            <span className="text-sm text-slate-600">
              已选中 <b>{selected.size}</b> 条
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setSelected(new Set())}
                className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
              >
                清空
              </button>
              <button
                disabled
                title="点评工作台将在 M2 交付"
                className="rounded bg-indigo-600 px-3 py-1 text-xs text-white opacity-50"
              >
                写点评（M2）
              </button>
            </div>
          </div>
        </div>
      )}

      <NewsDetailDrawer
        item={items.find((i) => i.id === openId) ?? null}
        onClose={() => setOpenId(null)}
      />

      {toast && (
        <div
          onClick={clearToast}
          className="fixed bottom-6 left-1/2 z-40 -translate-x-1/2 rounded-full bg-slate-900 px-4 py-2 text-xs text-white shadow-lg"
        >
          {toast}
        </div>
      )}
    </div>
  )
}
