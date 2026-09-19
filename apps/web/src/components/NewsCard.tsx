import { Link } from 'react-router-dom'
import type { NewsItem } from '../lib/api'
import { contentTypeLabel, formatTime, importanceTier, industryLabel } from '../lib/format'
import { Badge, cn } from './ui'

interface Props {
  item: NewsItem
  active?: boolean
  selected?: boolean
  starred?: boolean
  onOpen: (item: NewsItem) => void
  onToggleSelect: (id: string) => void
  onStar: (item: NewsItem) => void
}

export function NewsCard({
  item,
  active,
  selected,
  starred,
  onOpen,
  onToggleSelect,
  onStar,
}: Props) {
  const tier = importanceTier(item.importance)
  const others = Math.max(0, item.source_count - 1)

  return (
    <article
      onClick={() => onOpen(item)}
      className={cn(
        'group cursor-pointer rounded-lg border border-slate-200 bg-white p-3 shadow-sm transition-all hover:border-slate-300 hover:shadow',
        active && 'card-active',
      )}
    >
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          checked={!!selected}
          onClick={(e) => e.stopPropagation()}
          onChange={() => onToggleSelect(item.id)}
          className="mt-1 h-4 w-4 shrink-0 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
          aria-label="选中这条资讯"
        />

        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
            <span className="font-medium text-slate-700">{item.source_name ?? '未知来源'}</span>
            <span>·</span>
            <span>{formatTime(item.published_at)}</span>
            <Badge className={tier.cls}>{tier.label}</Badge>
            <Badge>{contentTypeLabel(item.content_type)}</Badge>
            {item.industries.slice(0, 3).map((i) => (
              <Badge key={i} className="bg-indigo-50 text-indigo-600">
                {industryLabel(i)}
              </Badge>
            ))}
            {/* 事件簇角标：跨源交叉验证的入口（docs/03 步骤②） */}
            {others > 0 && (
              <Badge className="bg-amber-50 text-amber-700" title="同一事件的其他报道">
                另有 {others} 家报道
              </Badge>
            )}
          </div>

          <h3 className="truncate text-[15px] font-semibold leading-6 text-slate-900 group-hover:text-indigo-700">
            {item.title}
          </h3>

          {item.summary && (
            <p className="mt-1 line-clamp-2 text-[13px] leading-5 text-slate-600">{item.summary}</p>
          )}
        </div>

        <button
          onClick={(e) => {
            e.stopPropagation()
            onStar(item)
          }}
          title="收藏 / 取消收藏"
          className={cn(
            'shrink-0 rounded p-1 text-lg leading-none transition-colors',
            starred ? 'text-amber-400' : 'text-slate-300 hover:text-amber-400',
          )}
        >
          ★
        </button>
      </div>

      <div className="mt-2 hidden gap-2 text-xs group-hover:flex">
        {item.url && (
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="text-slate-500 hover:text-indigo-600"
          >
            原文 ↗
          </a>
        )}
        <Link
          to={`/news/${item.id}`}
          onClick={(e) => e.stopPropagation()}
          className="text-slate-500 hover:text-indigo-600"
        >
          整页详情 →
        </Link>
      </div>
    </article>
  )
}
