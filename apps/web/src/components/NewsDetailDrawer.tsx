import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import { api, type NewsItem } from '../lib/api'
import { NewsDetail } from './NewsDetail'

/** 详情抽屉：点卡片即开，不打断浏览（docs/03 步骤②「详情抽屉」）。 */
export function NewsDetailDrawer({
  item,
  onClose,
}: {
  item: NewsItem | null
  onClose: () => void
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['news', item?.id],
    queryFn: () => api.getNews(item!.id),
    enabled: !!item,
  })

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!item) return null

  return (
    <>
      <div className="fixed inset-0 z-20 bg-slate-900/20" onClick={onClose} />
      <aside className="fixed right-0 top-0 z-30 flex h-full w-full max-w-xl flex-col border-l border-slate-200 bg-white shadow-xl">
        <header className="flex items-center justify-between border-b border-slate-200 px-4 py-2.5">
          <span className="text-xs text-slate-500">资讯详情</span>
          <button
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            aria-label="关闭"
          >
            ✕
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-4">
          <NewsDetail data={data} loading={isLoading} error={error as Error | null} />
        </div>
      </aside>
    </>
  )
}
