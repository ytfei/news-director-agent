import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { Markdown } from '../components/Markdown'
import { toast } from '../components/Toast'
import { Badge, Button, EmptyState, ErrorState, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { formatDateTime } from '../lib/format'

/** 稿件库：列表。 */
export function Articles() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['articles'],
    queryFn: () => api.listArticles(),
  })

  if (isLoading)
    return (
      <div className="flex items-center gap-2 p-6 text-sm text-slate-500">
        <Spinner /> 加载中…
      </div>
    )
  if (error)
    return (
      <div className="p-6">
        <ErrorState message={(error as Error).message} />
      </div>
    )
  if (!data?.length)
    return (
      <div className="p-6">
        <EmptyState
          title="还没有稿件"
          hint="去选题页挑好素材，触发写作后成稿会出现在这里"
        />
      </div>
    )

  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="mb-4 text-base font-semibold text-slate-900">稿件库</h1>
      <div className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
        {data.map((a) => (
          <Link
            key={a.id}
            to={`/articles/${a.id}`}
            className="flex items-center gap-3 p-3 hover:bg-slate-50"
          >
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] font-medium text-slate-800">{a.title}</div>
              <div className="mt-0.5 text-[11px] text-slate-400">
                {formatDateTime(a.created_at)} · {a.current_version_no} 个版本
              </div>
            </div>
            <Badge className="bg-slate-100 text-slate-600">{a.word_count} 字</Badge>
          </Link>
        ))}
      </div>
    </div>
  )
}

/** 稿件详情：正文 + 段落溯源 + 版本历史。 */
export function ArticlePage() {
  const { id } = useParams()
  const { data, isLoading, error } = useQuery({
    queryKey: ['article', id],
    queryFn: () => api.getArticle(id as string),
    enabled: !!id,
  })

  if (isLoading)
    return (
      <div className="flex items-center gap-2 p-6 text-sm text-slate-500">
        <Spinner /> 加载中…
      </div>
    )
  if (error)
    return (
      <div className="p-6">
        <ErrorState message={(error as Error).message} />
      </div>
    )
  if (!data) return null

  const sections = data.citation_map?.sections ?? {}

  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Link to="/articles" className="text-xs text-slate-500 hover:text-indigo-600">
          ← 返回稿件库
        </Link>
        <h1 className="text-base font-semibold text-slate-900">{data.title}</h1>
        <Badge className="bg-emerald-50 text-emerald-700">{data.word_count} 字</Badge>
        {data.citation_map?.brief_mode && (
          <Badge className="bg-slate-100 text-slate-600">
            {data.citation_map.brief_mode === 'opinion' ? '观点驱动' : '素材综述'}
          </Badge>
        )}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <Markdown text={data.content} />

        {Object.keys(sections).length > 0 && (
          <div className="mt-6 border-t border-slate-100 pt-3">
            <div className="mb-1 text-[11px] font-medium text-slate-600">
              ★ 段落溯源（这段话依据哪些素材）
            </div>
            <div className="space-y-1">
              {Object.entries(sections).map(([key, v]) => (
                <div key={key} className="text-[11px] text-slate-500">
                  <span className="text-slate-700">{v.heading}</span>
                  {v.material_refs.length > 0
                    ? ` → 素材 #${v.material_refs.join(' #')}`
                    : ' → 未绑定素材'}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 flex gap-2">
        <Button
          variant="outline"
          onClick={() => {
            void navigator.clipboard.writeText(data.content)
            toast('已复制全文')
          }}
        >
          复制全文
        </Button>
      </div>

      {data.versions.length > 0 && (
        <div className="mt-5">
          <div className="mb-1 text-[11px] font-medium text-slate-600">版本历史</div>
          <div className="divide-y divide-slate-100 rounded border border-slate-200">
            {data.versions.map((v) => (
              <div key={v.version_no} className="flex items-center gap-2 p-2 text-[11px]">
                <span className="rounded bg-slate-100 px-1.5 text-slate-600">v{v.version_no}</span>
                <span className="text-slate-500">{v.source}</span>
                <span className="text-slate-400">{v.word_count} 字</span>
                <span className="ml-auto text-slate-400">{formatDateTime(v.created_at)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
