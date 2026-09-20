import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { Badge, Button, ErrorState, Spinner, cn } from '../components/ui'
import { api } from '../lib/api'

const STAGES = ['素材装载', '大纲', '分段写作', '事实复核', '成稿']

/**
 * AI 写作（M3 占位）。
 *
 * 已实现的部分：准入校验（后端 `POST /projects/{id}/compose`）与 run 建档。
 * 未实现：compose_graph（大纲 HITL → 分段流式 → 风格统一 → citation_map）。
 * 这一页刻意不画假界面：只呈现 WriterAgent 会读到的**输入**（brief 的真实内容）。
 */
export function Compose() {
  const { id } = useParams()
  const { data, isLoading, error } = useQuery({
    queryKey: ['project', id],
    queryFn: () => api.getProject(id as string),
    enabled: !!id,
  })

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 p-6 text-sm text-slate-500">
        <Spinner /> 加载中…
      </div>
    )
  }
  if (error) return <div className="p-6"><ErrorState message={(error as Error).message} /></div>
  if (!data) return null

  const withAnn = data.materials.filter((m) => m.annotation)

  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Link to="/projects" className="text-xs text-slate-500 hover:text-indigo-600">
          ← 返回选题
        </Link>
        <h1 className="text-base font-semibold text-slate-900">{data.title}</h1>
        <Badge className={data.assessment.mode === 'opinion' ? 'bg-indigo-50 text-indigo-700' : 'bg-amber-50 text-amber-700'}>
          {data.assessment.mode === 'opinion' ? '观点驱动' : '素材综述'}
        </Badge>
      </div>

      {/* 阶段条（灰态：等待 compose_graph） */}
      <div className="mb-5 flex items-center gap-0">
        {STAGES.map((s, i) => (
          <div key={s} className="flex-1 text-center">
            <div
              className={cn('h-1 rounded', i === 0 ? 'bg-indigo-500' : 'bg-slate-200')}
            />
            <div className={cn('mt-1 text-[11px]', i === 0 ? 'text-indigo-700' : 'text-slate-400')}>
              {s}
            </div>
          </div>
        ))}
      </div>

      <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-800">
        <b>compose_graph 尚未接入。</b>
        后端已完成准入校验并建立了 <code className="rounded bg-white/70 px-1">agent_runs</code> 记录（status=queued）。
        接入 LangGraph 后，这一页会依次出现：大纲 <code className="rounded bg-white/70 px-1">interrupt</code> 等待确认
        → 分段流式输出（SSE）→ 事实复核结果 → 成稿与 <code className="rounded bg-white/70 px-1">citation_map</code>。
      </div>

      {/* 素材装载：WriterAgent 的真实输入 */}
      <div className="rounded-lg border border-slate-200 bg-white">
        <div className="border-b border-slate-100 px-3 py-2 text-xs font-semibold text-slate-700">
          素材装载（brief 的真实内容）
        </div>
        <div className="p-3">
          <div className="mb-3 font-mono text-[11px] leading-6 text-slate-500">
            <div>/</div>
            <div>├─ brief.md　　选题简报（{data.materials.length} 条素材，其中 {withAnn.length} 条带点评）</div>
            <div>├─ facts/　　　（有 FactCard 的资讯才会出现）</div>
            <div>├─ style-guide.md　　{data.prompts.map((p) => `${p.name} v${p.version_no}`).join(' + ') || '未选择提示词'}</div>
            <div>└─ draft/　　　（待写入）</div>
          </div>

          <div className="mb-2 text-[11px] font-medium text-slate-600">素材清单</div>
          <div className="divide-y divide-slate-100 rounded border border-slate-200">
            {data.materials.map((m) => (
              <div key={m.id} className="p-2">
                <div className="flex items-start gap-2">
                  <span className="rounded bg-indigo-600 px-1.5 text-[11px] font-semibold text-white">
                    {m.score}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-xs font-medium text-slate-800">{m.news?.title}</div>
                    {m.annotation ? (
                      <div className="mt-0.5 text-[11px] leading-5 text-slate-500">{m.annotation.body}</div>
                    ) : (
                      <div className="mt-0.5 text-[11px] text-slate-400">无点评 · 仅作背景事实</div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {data.require_note && (
            <div className="mt-3 rounded bg-slate-50 p-2 text-[11px] text-slate-600">
              <b>写作要求：</b>
              {data.require_note}
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 flex gap-2">
        <Button variant="primary" disabled title="等待 compose_graph 接入">
          确认大纲并开始写作（M3）
        </Button>
        <Link to="/projects">
          <Button variant="outline">调整素材</Button>
        </Link>
      </div>
    </div>
  )
}
