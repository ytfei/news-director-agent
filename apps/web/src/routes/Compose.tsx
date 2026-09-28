import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Markdown } from '../components/Markdown'
import { toast } from '../components/Toast'
import { Badge, Button, ErrorState, Spinner, cn } from '../components/ui'
import { api, type AgentRun, type Outline, type OutlineSection } from '../lib/api'

const STAGES = ['素材', '大纲', '确认', '写作', '成稿']

function stageOf(run: AgentRun | undefined): number {
  switch (run?.status) {
    case 'queued':
    case 'running':
      return 1
    case 'waiting_human':
      return 2
    case 'succeeded':
      return 4
    case 'failed':
    case 'cancelled':
      return 2
    default:
      return 0
  }
}

function StageBar({ index, failed }: { index: number; failed: boolean }) {
  return (
    <div className="mb-5 flex items-center">
      {STAGES.map((s, i) => (
        <div key={s} className="flex-1 text-center">
          <div
            className={cn(
              'h-1 rounded',
              i < index && 'bg-indigo-500',
              i === index && (failed ? 'bg-rose-500' : 'bg-indigo-500 animate-pulse'),
              i > index && 'bg-slate-200',
            )}
          />
          <div
            className={cn(
              'mt-1 text-[11px]',
              i <= index ? 'text-indigo-700' : 'text-slate-400',
            )}
          >
            {s}
          </div>
        </div>
      ))}
    </div>
  )
}

/** 大纲确认卡：标题可改选、段落标题可编辑 —— 这是 HITL 的核心交互。 */
function OutlineCard({
  outline,
  title,
  onTitle,
  onOutline,
  onConfirm,
  onReset,
  busy,
}: {
  outline: Outline
  title: string
  onTitle: (v: string) => void
  onOutline: (o: Outline) => void
  onConfirm: () => void
  onReset: () => void
  busy: boolean
}) {
  const setHeading = (i: number, heading: string) => {
    const sections = outline.sections.map((s: OutlineSection, idx: number) =>
      idx === i ? { ...s, heading } : s,
    )
    onOutline({ ...outline, sections })
  }

  return (
    <div className="rounded-lg border border-indigo-200 bg-white">
      <div className="flex items-center justify-between border-b border-indigo-100 bg-indigo-50/60 px-3 py-2">
        <span className="text-xs font-semibold text-indigo-900">大纲已生成 · 确认后再写正文</span>
        <Badge className="bg-indigo-100 text-indigo-700">{outline.sections.length} 段</Badge>
      </div>

      <div className="space-y-4 p-3">
        <div>
          <div className="mb-1 text-[11px] font-medium text-slate-600">标题</div>
          <input
            value={title}
            onChange={(e) => onTitle(e.target.value)}
            className="w-full rounded border border-slate-300 px-2 py-1.5 text-[13px] outline-none focus:border-indigo-500"
          />
          {outline.title_candidates.length > 1 && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {outline.title_candidates.map((c) => (
                <button
                  key={c}
                  onClick={() => onTitle(c)}
                  className={cn(
                    'rounded border px-1.5 py-0.5 text-[11px]',
                    c === title
                      ? 'border-indigo-300 bg-indigo-50 text-indigo-700'
                      : 'border-slate-200 text-slate-500 hover:border-indigo-300',
                  )}
                >
                  {c}
                </button>
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="mb-1 text-[11px] font-medium text-slate-600">段落（可直接改小标题）</div>
          <div className="space-y-2">
            {outline.sections.map((s, i) => (
              <div key={i} className="rounded border border-slate-200 p-2">
                <input
                  value={s.heading}
                  onChange={(e) => setHeading(i, e.target.value)}
                  className="w-full rounded border border-transparent px-1 py-0.5 text-[13px] font-medium text-slate-800 outline-none hover:border-slate-200 focus:border-indigo-500"
                />
                {s.key_points.length > 0 && (
                  <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[11px] leading-5 text-slate-500">
                    {s.key_points.map((k, j) => (
                      <li key={j}>{k}</li>
                    ))}
                  </ul>
                )}
                <div className="mt-1 text-[10px] text-slate-400">
                  约 {s.target_words} 字
                  {s.material_refs.length > 0 && ` · 引用素材 #${s.material_refs.join(' #')}`}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="flex gap-2 border-t border-slate-100 px-3 py-2">
        <Button variant="primary" onClick={onConfirm} disabled={busy}>
          {busy ? '写作中…' : '确认大纲并开始写作'}
        </Button>
        <Button variant="outline" onClick={onReset} disabled={busy}>
          放弃重来
        </Button>
      </div>
    </div>
  )
}

export function Compose() {
  const { id } = useParams()
  const qc = useQueryClient()
  const storageKey = `compose_run_${id}`

  // ★ runId 存本地：刷新页面不丢进度（worker 是异步的，用户很可能中途刷新）
  const [runId, setRunId] = useState<string | null>(() => localStorage.getItem(storageKey))
  const [draft, setDraft] = useState<Outline | null>(null)
  const [title, setTitle] = useState('')

  const project = useQuery({
    queryKey: ['project', id],
    queryFn: () => api.getProject(id as string),
    enabled: !!id,
  })

  const run = useQuery({
    queryKey: ['run', runId],
    queryFn: () => api.getRun(runId as string),
    enabled: !!runId,
    // 只在「还没出结果」时轮询；waiting_human 是等用户操作，不必轮询
    refetchInterval: (q) => {
      const s = q.state.data?.status
      return s === 'queued' || s === 'running' ? 2000 : false
    },
  })

  const articleId = (run.data?.output?.article_id as string | undefined) ?? null
  const article = useQuery({
    queryKey: ['article', articleId],
    queryFn: () => api.getArticle(articleId as string),
    enabled: !!articleId,
  })

  // 大纲出来后建立一份可编辑副本（不直接改服务端数据）
  const serverOutline = run.data?.interrupt_payload?.outline
  useEffect(() => {
    if (serverOutline) {
      setDraft((prev) => prev ?? structuredClone(serverOutline))
      setTitle((prev) => prev || serverOutline.title_candidates[0] || '')
    }
  }, [serverOutline])

  useEffect(() => {
    if (runId) localStorage.setItem(storageKey, runId)
    else localStorage.removeItem(storageKey)
  }, [runId, storageKey])

  const start = useMutation({
    mutationFn: (sync: boolean) => api.composeProject(id as string, sync),
    onSuccess: (r) => {
      setRunId(r.run_id)
      toast(r.async === false ? '大纲已生成' : '已入队，正在生成大纲…')
      void qc.invalidateQueries({ queryKey: ['run', r.run_id] })
    },
    onError: (e) => toast(`触发失败：${(e as Error).message}`),
  })

  const resume = useMutation({
    mutationFn: (sync: boolean) =>
      api.resumeRun(runId as string, draft ?? undefined, sync),
    onSuccess: (r) => {
      toast(r.async === false ? '成稿完成' : '已开始写作，分段生成中…')
      void qc.invalidateQueries({ queryKey: ['run', runId] })
    },
    onError: (e) => toast(`写作失败：${(e as Error).message}`),
  })

  const reset = () => {
    setRunId(null)
    setDraft(null)
    setTitle('')
  }

  if (project.isLoading) {
    return (
      <div className="flex items-center gap-2 p-6 text-sm text-slate-500">
        <Spinner /> 加载中…
      </div>
    )
  }
  if (project.error)
    return (
      <div className="p-6">
        <ErrorState message={(project.error as Error).message} />
      </div>
    )
  const data = project.data
  if (!data) return null

  const status = run.data?.status
  const failed = status === 'failed' || status === 'cancelled'
  const busy = start.isPending || resume.isPending

  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Link to="/projects" className="text-xs text-slate-500 hover:text-indigo-600">
          ← 返回选题
        </Link>
        <h1 className="text-base font-semibold text-slate-900">{data.title}</h1>
        <Badge
          className={
            data.assessment.mode === 'opinion'
              ? 'bg-indigo-50 text-indigo-700'
              : 'bg-amber-50 text-amber-700'
          }
        >
          {data.assessment.mode === 'opinion' ? '观点驱动' : '素材综述'}
        </Badge>
        {status && <Badge className="bg-slate-100 text-slate-600">{status}</Badge>}
      </div>

      <StageBar index={status ? stageOf(run.data) : 0} failed={failed} />

      {/* ---------- 未开始：展示 brief，让用户知道 AI 会拿什么去写 ---------- */}
      {!runId && (
        <div className="rounded-lg border border-slate-200 bg-white">
          <div className="border-b border-slate-100 px-3 py-2 text-xs font-semibold text-slate-700">
            素材装载（WriterAgent 的真实输入）
          </div>
          <div className="p-3">
            <div className="mb-3 rounded bg-slate-50 p-2 font-mono text-[11px] leading-6 text-slate-500">
              <div>brief.md　{data.materials.length} 条素材 · 模式 {data.assessment.mode}</div>
              <div>style-guide.md　{data.prompts.map((p) => `${p.name} v${p.version_no}`).join(' + ') || '未选择提示词'}</div>
              <div>draft/　（待写入）</div>
            </div>
            <div className="divide-y divide-slate-100 rounded border border-slate-200">
              {data.materials.map((m) => (
                <div key={m.id} className="p-2">
                  <div className="flex items-start gap-2">
                    <span className="rounded bg-indigo-600 px-1.5 text-[11px] font-semibold text-white">
                      {m.score}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-xs font-medium text-slate-800">
                        {m.news?.title}
                      </div>
                      {m.annotation ? (
                        <div className="mt-0.5 text-[11px] leading-5 text-slate-500">
                          {m.annotation.body}
                        </div>
                      ) : (
                        <div className="mt-0.5 text-[11px] text-slate-400">
                          无点评 · 仅作背景事实
                        </div>
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
          <div className="flex gap-2 border-t border-slate-100 px-3 py-2">
            <Button
              variant="primary"
              onClick={() => start.mutate(false)}
              disabled={busy || !data.assessment.writable}
            >
              {busy ? '提交中…' : '生成大纲'}
            </Button>
            <Button variant="outline" onClick={() => start.mutate(true)} disabled={busy}>
              同步执行（未起 worker 时用）
            </Button>
            {!data.assessment.writable && (
              <span className="self-center text-[11px] text-rose-600">
                {data.assessment.blocking_reasons.join('；')}
              </span>
            )}
          </div>
        </div>
      )}

      {/* ---------- 生成中 ---------- */}
      {runId && (status === 'queued' || status === 'running') && (
        <div className="rounded-lg border border-slate-200 bg-white p-6 text-center">
          <div className="flex items-center justify-center gap-2 text-sm text-slate-600">
            <Spinner /> 正在生成大纲（pro 档推理，约 30~60 秒）
          </div>
          <div className="mt-2 text-[11px] text-slate-400">
            若长时间无进展，可能是 worker 未启动 —— 请运行 <code>make worker</code>，
            或返回上一步改用「同步执行」。
          </div>
        </div>
      )}

      {/* ---------- 等待确认大纲（HITL 中断点）---------- */}
      {status === 'waiting_human' && draft && (
        <OutlineCard
          outline={draft}
          title={title}
          onTitle={setTitle}
          onOutline={setDraft}
          onConfirm={() => resume.mutate(false)}
          onReset={reset}
          busy={resume.isPending}
        />
      )}

      {/* ---------- 成稿 ---------- */}
      {status === 'succeeded' && (
        <div className="rounded-lg border border-slate-200 bg-white">
          <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
            <span className="text-xs font-semibold text-slate-700">
              {article.data?.title ?? '成稿'}
            </span>
            {article.data && (
              <Badge className="bg-emerald-50 text-emerald-700">
                {article.data.word_count} 字
              </Badge>
            )}
          </div>
          <div className="p-4">
            {article.isLoading ? (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <Spinner /> 加载稿件…
              </div>
            ) : article.data ? (
              <>
                <Markdown text={article.data.content} />
                {Object.keys(article.data.citation_map?.sections ?? {}).length > 0 && (
                  <div className="mt-5 border-t border-slate-100 pt-3">
                    <div className="mb-1 text-[11px] font-medium text-slate-600">
                      ★ 段落溯源（这段话依据哪些素材）
                    </div>
                    <div className="space-y-1">
                      {Object.entries(article.data.citation_map.sections ?? {}).map(
                        ([key, v]) => (
                          <div key={key} className="text-[11px] text-slate-500">
                            <span className="text-slate-700">{v.heading}</span>
                            {v.material_refs.length > 0
                              ? ` → 素材 #${v.material_refs.join(' #')}`
                              : ' → 未绑定素材'}
                          </div>
                        ),
                      )}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="text-sm text-slate-500">稿件加载失败</div>
            )}
          </div>
          <div className="flex gap-2 border-t border-slate-100 px-3 py-2">
            <Button
              variant="outline"
              onClick={() => {
                if (article.data) {
                  void navigator.clipboard.writeText(article.data.content)
                  toast('已复制全文')
                }
              }}
            >
              复制全文
            </Button>
            <Button variant="outline" onClick={reset}>
              重新写作
            </Button>
          </div>
        </div>
      )}

      {/* ---------- 失败 ---------- */}
      {failed && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4">
          <ErrorState message={run.data?.error_message ?? '写作失败'} onRetry={reset} />
        </div>
      )}

      {/* token 消耗：成本可见性 */}
      {run.data && (run.data.token_input || run.data.token_output) > 0 && (
        <div className="mt-3 text-[11px] text-slate-400">
          本次消耗 token：{run.data.token_input} in / {run.data.token_output} out
        </div>
      )}
    </div>
  )
}
