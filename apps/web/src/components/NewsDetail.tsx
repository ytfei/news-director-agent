import { Link } from 'react-router-dom'
import type { NewsDetail as Detail } from '../lib/api'
import { contentTypeLabel, formatDateTime, importanceTier, industryLabel } from '../lib/format'
import { Badge, Spinner } from './ui'

/** 详情内容：抽屉与整页复用。 */
export function NewsDetail({
  data,
  loading,
  error,
}: {
  data: Detail | undefined
  loading: boolean
  error: Error | null
}) {
  if (loading)
    return (
      <div className="flex items-center gap-2 p-6 text-sm text-slate-500">
        <Spinner /> 加载中…
      </div>
    )
  if (error) return <div className="p-6 text-sm text-rose-600">{error.message}</div>
  if (!data) return <div className="p-6 text-sm text-slate-500">请选择一条资讯</div>

  const tier = importanceTier(data.importance)

  return (
    <div className="space-y-4">
      <div>
        <div className="mb-1.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
          <span className="font-medium text-slate-700">{data.source_name ?? '未知来源'}</span>
          <span>·</span>
          <span>{formatDateTime(data.published_at)}</span>
          <Badge className={tier.cls}>{tier.label}</Badge>
          <Badge>{contentTypeLabel(data.content_type)}</Badge>
          {data.industries.map((i) => (
            <Badge key={i} className="bg-indigo-50 text-indigo-600">
              {industryLabel(i)}
            </Badge>
          ))}
        </div>
        <h2 className="text-lg font-semibold leading-7 text-slate-900">{data.title}</h2>
        {data.url && (
          <a
            href={data.url}
            target="_blank"
            rel="noreferrer"
            className="mt-1 inline-block text-xs text-indigo-600 hover:underline"
          >
            查看原文 ↗
          </a>
        )}
      </div>

      {/* 事件簇：同一事件的其他来源 —— 跨源交叉验证的入口 */}
      {data.siblings.length > 0 && (
        <section className="rounded-lg border border-amber-200 bg-amber-50/60 p-3">
          <h4 className="mb-1.5 text-xs font-semibold text-amber-800">
            另有 {data.siblings.length} 家报道（同一事件）
          </h4>
          <ul className="space-y-1">
            {data.siblings.slice(0, 10).map((s) => (
              <li key={s.id} className="flex items-baseline gap-2 text-xs">
                <span className="shrink-0 text-slate-500">{s.source_name ?? '未知'}</span>
                <Link
                  to={`/news/${s.id}`}
                  className="line-clamp-1 text-slate-700 hover:text-indigo-600"
                >
                  {s.title}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.source_refs.length > 0 && (
        <section>
          <h4 className="mb-1.5 text-xs font-semibold text-slate-500">
            来源登记（{data.source_refs.length}）
          </h4>
          <ul className="space-y-1 text-xs text-slate-600">
            {data.source_refs.map((r, i) => (
              <li key={i} className="truncate">
                · {r.source_name ?? r.external_id}
              </li>
            ))}
          </ul>
        </section>
      )}

      <article className="whitespace-pre-wrap text-[13px] leading-6 text-slate-700">
        {data.content ?? data.summary ?? '（无正文）'}
      </article>
    </div>
  )
}
