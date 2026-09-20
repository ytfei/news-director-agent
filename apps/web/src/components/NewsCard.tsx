import type { AnnotationBrief, MaterialBadge, NewsItem } from '../lib/api'
import { contentTypeLabel, formatTime, importanceTier, industryLabel } from '../lib/format'
import { Badge, Button, cn } from './ui'

interface Props {
  item: NewsItem
  material?: MaterialBadge | null
  annotation?: AnnotationBrief | null
  active?: boolean
  selected?: boolean
  starred?: boolean
  onOpen: (item: NewsItem) => void
  onToggleSelect: (id: string) => void
  onStar: (item: NewsItem) => void
  onMarkMaterial: () => void
  onAnnotate: () => void
  onRemoveMaterial?: () => void
}

const VERDICT_BADGE: Record<string, { text: string; cls: string }> = {
  passed: { text: '通过', cls: 'bg-emerald-50 text-emerald-700' },
  needs_revision: { text: '需修改', cls: 'bg-amber-50 text-amber-700' },
  blocked: { text: '有红线', cls: 'bg-rose-50 text-rose-700' },
}

export function NewsCard({
  item,
  material,
  annotation,
  active,
  selected,
  starred,
  onOpen,
  onToggleSelect,
  onStar,
  onMarkMaterial,
  onAnnotate,
  onRemoveMaterial,
}: Props) {
  const tier = importanceTier(item.importance)
  const others = Math.max(0, (item.source_count ?? 1) - 1)
  const verdict = annotation?.verdict
  const vb = verdict ? VERDICT_BADGE[verdict] : null

  return (
    <article
      onClick={() => onOpen(item)}
      className={cn(
        'group cursor-pointer rounded-lg border bg-white p-3 shadow-sm transition-all hover:border-slate-300 hover:shadow',
        material ? 'border-indigo-200' : 'border-slate-200',
        active && 'card-active',
        selected && 'ring-1 ring-indigo-300',
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
            {others > 0 && (
              <Badge className="bg-amber-50 text-amber-700" title="同一事件的其他报道">
                另有 {others} 家报道
              </Badge>
            )}
            {material && (
              <Badge className="bg-indigo-600 text-white" title="已加入素材库">
                🔖 素材 {material.score}/10
              </Badge>
            )}
            {vb && <Badge className={vb.cls}>批注 · {vb.text}</Badge>}
          </div>

          <h3 className="truncate text-[15px] font-semibold leading-6 text-slate-900 group-hover:text-indigo-700">
            {item.title}
          </h3>

          {item.summary && (
            <p className="mt-1 line-clamp-2 text-[13px] leading-5 text-slate-600">{item.summary}</p>
          )}

          {material && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5 rounded bg-indigo-50/60 px-2 py-1.5">
              <span className="rounded bg-indigo-600 px-1.5 text-[11px] font-semibold text-white">
                {material.score}
              </span>
              {material.topics.length ? (
                material.topics.map((t) => (
                  <Badge key={t} className="bg-white text-indigo-700">
                    {t}
                  </Badge>
                ))
              ) : (
                <span className="text-[11px] text-slate-400">未设主题</span>
              )}
              <Badge className="bg-white text-slate-500">{material.material_date}</Badge>
              <div className="ml-auto flex gap-1">
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    onMarkMaterial()
                  }}
                  className="rounded px-1.5 py-0.5 text-[11px] text-slate-500 hover:bg-white hover:text-indigo-600"
                >
                  改评分/主题
                </button>
                {onRemoveMaterial && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      onRemoveMaterial()
                    }}
                    className="rounded px-1.5 py-0.5 text-[11px] text-slate-400 hover:bg-white hover:text-rose-600"
                  >
                    移出素材
                  </button>
                )}
              </div>
            </div>
          )}

          {annotation?.body && (
            <p className="mt-2 line-clamp-2 border-l-2 border-slate-200 pl-2 text-[12px] leading-5 text-slate-500">
              {annotation.body}
            </p>
          )}
        </div>

        <div className="flex shrink-0 flex-col items-end gap-1">
          <button
            onClick={(e) => {
              e.stopPropagation()
              onStar(item)
            }}
            title="收藏 / 取消收藏"
            className={cn(
              'rounded p-1 text-lg leading-none transition-colors',
              starred ? 'text-amber-400' : 'text-slate-300 hover:text-amber-400',
            )}
          >
            ★
          </button>
          <Button
            size="sm"
            variant={material ? 'outline' : 'primary'}
            onClick={(e) => {
              e.stopPropagation()
              onMarkMaterial()
            }}
          >
            {material ? '编辑素材' : '🔖 加入素材'}
          </Button>
          <Button
            size="sm"
            variant={annotation ? 'outline' : 'outline'}
            onClick={(e) => {
              e.stopPropagation()
              onAnnotate()
            }}
          >
            {annotation ? '查看批注' : '✍️ 批注'}
          </Button>
        </div>
      </div>
    </article>
  )
}
