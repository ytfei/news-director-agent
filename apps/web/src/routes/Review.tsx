import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Badge, Button, EmptyState, ErrorState, Spinner, cn } from '../components/ui'
import { useResolveFinding } from '../hooks/useWorkspace'
import { api, type Finding, type ReviewReport } from '../lib/api'

const TRACK: Record<string, { text: string; cls: string }> = {
  fact: { text: '事实', cls: 'bg-cyan-50 text-cyan-700' },
  logic: { text: '逻辑', cls: 'bg-indigo-50 text-indigo-700' },
  compliance: { text: '合规', cls: 'bg-rose-50 text-rose-700' },
  tone: { text: '语气', cls: 'bg-slate-100 text-slate-600' },
  uniqueness: { text: '独特性', cls: 'bg-slate-100 text-slate-600' },
}

const SEVERITY: Record<string, { text: string; cls: string; bar: string }> = {
  blocker: { text: '红线', cls: 'bg-rose-100 text-rose-700', bar: 'border-l-rose-500' },
  high: { text: '严重', cls: 'bg-orange-100 text-orange-700', bar: 'border-l-orange-400' },
  medium: { text: '中等', cls: 'bg-amber-100 text-amber-700', bar: 'border-l-amber-300' },
  low: { text: '轻微', cls: 'bg-cyan-100 text-cyan-700', bar: 'border-l-cyan-300' },
  info: { text: '提示', cls: 'bg-slate-100 text-slate-500', bar: 'border-l-slate-300' },
}

const VERDICT: Record<string, { text: string; cls: string }> = {
  passed: { text: '通过', cls: 'border-emerald-200 bg-emerald-50 text-emerald-700' },
  needs_revision: { text: '需修改', cls: 'border-amber-200 bg-amber-50 text-amber-700' },
  blocked: { text: '有红线', cls: 'border-rose-200 bg-rose-50 text-rose-700' },
}

/**
 * 体检报告：三轨发现项的处置台（docs/03 步骤⑦）。
 *
 * 交互契约：
 * - 采纳 → 用 suggestion 替换正文并生成新版本，需要复检
 * - 驳回 → 必填理由，之后**同一问题不再重复报**
 * - 忽略 → 只关闭 finding，不改正文
 */
export function Review() {
  const { reportId } = useParams()
  const [params] = useSearchParams()
  const [activeMaterial, setActiveMaterial] = useState<string | null>(params.get('material'))
  const [reason, setReason] = useState<{ id: string; text: string } | null>(null)

  const resolve = useResolveFinding()

  const materialsQuery = useQuery({
    queryKey: ['materials', 'review'],
    queryFn: () => api.listMaterials({ has_annotation: true, limit: 200 }),
  })
  const materials = materialsQuery.data ?? []

  useEffect(() => {
    if (activeMaterial) return
    if (materials.length) setActiveMaterial(materials[0].id)
  }, [materials, activeMaterial])

  const directQuery = useQuery({
    queryKey: ['report', reportId],
    queryFn: () => api.getReport(reportId as string),
    enabled: !!reportId,
  })

  const reportsQuery = useQuery({
    queryKey: ['reports', activeMaterial],
    queryFn: () => api.listReports({ material_id: activeMaterial as string }),
    enabled: !!activeMaterial && !reportId,
  })

  const report: ReviewReport | null = reportId
    ? (directQuery.data ?? null)
    : (reportsQuery.data?.[0] ?? null)
  const loading = reportId ? directQuery.isLoading : reportsQuery.isLoading
  const error = reportId ? directQuery.error : reportsQuery.error

  const openFindings = useMemo(
    () => (report?.findings ?? []).filter((f) => f.status === 'open'),
    [report],
  )
  const blockerCount = openFindings.filter((f) => f.severity === 'blocker').length
  const canWrite = !!report && blockerCount === 0

  return (
    <div className="grid h-full grid-cols-[260px_minmax(0,1fr)]">
      {/* 左：有批注的素材 */}
      <aside className="overflow-y-auto border-r border-slate-200 bg-white p-2">
        <div className="px-1 pb-2 text-[11px] font-medium text-slate-500">
          写过批注的素材（{materials.length}）
        </div>
        {materialsQuery.isLoading && (
          <div className="flex items-center gap-2 p-2 text-xs text-slate-500">
            <Spinner /> 加载中…
          </div>
        )}
        {!materialsQuery.isLoading && materials.length === 0 && (
          <div className="p-2 text-[11px] text-slate-400">
            还没有批注。去资讯中心写一条，再提交检查。
          </div>
        )}
        <div className="space-y-1">
          {materials.map((m) => {
            const v = m.annotation?.verdict
            const vb = v ? VERDICT[v] : null
            return (
              <Link
                key={m.id}
                to="/reviews"
                onClick={() => {
                  setActiveMaterial(m.id)
                  setReason(null)
                }}
                className={cn(
                  'block rounded-md border p-2 transition-colors',
                  m.id === activeMaterial
                    ? 'border-indigo-400 bg-indigo-50'
                    : 'border-slate-200 hover:border-slate-300',
                )}
              >
                <div className="flex items-start gap-1.5">
                  <span className="rounded bg-indigo-600 px-1.5 text-[11px] font-semibold text-white">
                    {m.score}
                  </span>
                  <span className="line-clamp-2 flex-1 text-xs font-medium text-slate-800">
                    {m.news?.title}
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-1">
                  {vb ? (
                    <Badge className={vb.cls}>{vb.text}</Badge>
                  ) : (
                    <Badge className="bg-slate-100 text-slate-400">未检查</Badge>
                  )}
                  {m.annotation && m.annotation.open_findings > 0 && (
                    <Badge className="bg-amber-50 text-amber-700">
                      待处理 {m.annotation.open_findings}
                    </Badge>
                  )}
                </div>
              </Link>
            )
          })}
        </div>
      </aside>

      {/* 右：报告 */}
      <section className="overflow-y-auto p-4">
        {loading && (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> 加载中…
          </div>
        )}
        {error && <ErrorState message={(error as Error).message} />}
        {!loading && !error && !report && (
          <EmptyState
            title="这条素材还没有体检报告"
            hint="在资讯中心或工作台点「提交检查」，三轨检查会生成报告。"
          />
        )}

        {report && (
          <>
            {/* 总评 */}
            <div
              className={cn(
                'mb-4 flex flex-wrap items-center gap-3 rounded-lg border p-3',
                VERDICT[report.verdict].cls,
              )}
            >
              <div>
                <div className="text-sm font-semibold">{VERDICT[report.verdict].text}</div>
                <div className="text-[11px] opacity-80">
                  {report.summary ?? '未发现问题'} · 检查版本 v{report.annotation_version_no} · 共{' '}
                  {report.findings_count} 项
                </div>
              </div>
              <div className="ml-auto flex flex-wrap items-center gap-2">
                {!canWrite && (
                  <span className="text-[11px]">
                    ⛔ 存在未处置的红线，禁止进入写作
                  </span>
                )}
                <Link to="/projects">
                  <Button size="sm" variant={canWrite ? 'primary' : 'outline'} disabled={!canWrite}>
                    📁 创建选题并写作
                  </Button>
                </Link>
              </div>
            </div>

            {/* 原文（划词高亮） */}
            {report.annotation && (
              <div className="mb-4 rounded-lg border border-slate-200 bg-white p-4">
                <div className="mb-2 flex items-center gap-2 text-[11px] text-slate-500">
                  <b className="text-slate-700">点评原文</b>
                  {report.news && <span className="truncate">{report.news.title}</span>}
                  <Badge className="ml-auto">v{report.annotation.version_no}</Badge>
                </div>
                <div className="text-[14px] leading-8 text-slate-800">
                  {highlight(report.annotation.body, openFindings)}
                </div>
              </div>
            )}

            {/* findings */}
            <div className="space-y-2">
              {report.findings.length === 0 && (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-700">
                  三轨检查未发现问题。
                </div>
              )}

              {report.findings.map((f) => {
                const sev = SEVERITY[f.severity]
                const track = TRACK[f.track]
                const done = f.status !== 'open'
                return (
                  <div
                    key={f.id}
                    className={cn(
                      'rounded-lg border border-slate-200 border-l-4 bg-white p-3',
                      sev.bar,
                      done && 'opacity-60',
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge className={track.cls}>{track.text}</Badge>
                      <Badge className={sev.cls}>{sev.text}</Badge>
                      {f.evidence.length > 0 && (
                        <Badge className="bg-emerald-50 text-emerald-700">带证据</Badge>
                      )}
                      {done && (
                        <Badge className="bg-slate-100 text-slate-500">
                          {f.status === 'accepted' ? '已采纳' : f.status === 'dismissed' ? '已驳回' : '已忽略'}
                        </Badge>
                      )}
                    </div>

                    {f.quote && (
                      <div className="mt-2 rounded border border-slate-200 bg-slate-50 px-2 py-1 text-[13px] text-slate-700">
                        {f.quote}
                      </div>
                    )}

                    <div className="mt-2 text-[13px] leading-6 text-slate-700">{f.message}</div>

                    {f.suggestion && (
                      <div className="mt-2 rounded border border-emerald-200 bg-emerald-50 px-2 py-1.5 text-[13px] text-emerald-800">
                        <b>建议替换为：</b>
                        {f.suggestion}
                      </div>
                    )}

                    {f.evidence.length > 0 && (
                      <div className="mt-2 space-y-1 text-[11px] text-slate-500">
                        {f.evidence.map((e, i) => (
                          <div key={i}>
                            来源：{String(e.src ?? '—')} · {String(e.date ?? '')}
                            {e.snippet ? ` ·「${String(e.snippet)}」` : ''}
                          </div>
                        ))}
                      </div>
                    )}

                    {f.status === 'dismissed' && f.reason && (
                      <div className="mt-2 rounded bg-slate-100 px-2 py-1 text-[11px] text-slate-500">
                        驳回理由：{f.reason}（同一问题不再重复报）
                      </div>
                    )}

                    {!done && (
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        {f.suggestion && (
                          <Button
                            size="sm"
                            variant="primary"
                            onClick={() => resolve.mutate({ findingId: f.id, action: 'accepted' })}
                            disabled={resolve.isPending}
                          >
                            ✅ 采纳建议
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            setReason(reason?.id === f.id ? null : { id: f.id, text: '' })
                          }
                        >
                          ✕ 驳回
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => resolve.mutate({ findingId: f.id, action: 'ignored' })}
                        >
                          忽略
                        </Button>
                      </div>
                    )}

                    {reason?.id === f.id && (
                      <div className="mt-2 rounded border border-slate-200 bg-slate-50 p-2">
                        <div className="mb-1 text-[11px] text-slate-500">
                          驳回必须填理由：它会进入历史，用于降低同类误报。
                        </div>
                        <textarea
                          value={reason.text}
                          onChange={(e) => setReason({ id: f.id, text: e.target.value })}
                          rows={2}
                          placeholder="例：这里的 30% 指的是单季度含税口径，我已核实过来源"
                          className="w-full rounded border border-slate-300 bg-white p-2 text-xs outline-none focus:border-indigo-500"
                        />
                        <div className="mt-1.5 flex gap-2">
                          <Button
                            size="sm"
                            variant="danger"
                            disabled={!reason.text.trim() || resolve.isPending}
                            onClick={() =>
                              resolve.mutate(
                                { findingId: f.id, action: 'dismissed', reason: reason.text.trim() },
                                { onSuccess: () => setReason(null) },
                              )
                            }
                          >
                            确认驳回
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setReason(null)}>
                            取消
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            <div className="mt-4 rounded-lg border border-slate-200 bg-white p-3 text-[11px] leading-5 text-slate-500">
              <b className="text-slate-700">三条轨道的阈值取向不同</b>
              ：合规高召回（宁可误报，命中红线即 blocker）、事实高精度（宁可漏报，只报基线里能对上的冲突）、
              逻辑折中（绝对化 high / 以偏概全 medium）。采纳会改写正文并生成新版本，因此建议随后复检一次。
            </div>
          </>
        )}
      </section>
    </div>
  )
}

/** 用 open findings 的 span 给原文划词高亮（severity 决定底色） */
function highlight(body: string, findings: Finding[]) {
  if (!body) return <span className="text-slate-400">（空）</span>
  const spans = findings
    .filter((f) => f.span_end > f.span_start)
    .sort((a, b) => a.span_start - b.span_start)

  const nodes: ReactNode[] = []
  let cursor = 0
  spans.forEach((f, i) => {
    if (f.span_start < cursor) return
    if (f.span_start > cursor) nodes.push(body.slice(cursor, f.span_start))
    nodes.push(
      <mark
        key={`${f.id}-${i}`}
        title={`${TRACK[f.track]?.text ?? f.track} · ${SEVERITY[f.severity]?.text ?? f.severity}`}
        className={cn(
          'rounded px-0.5',
          f.severity === 'blocker'
            ? 'bg-rose-200/70'
            : f.severity === 'high'
              ? 'bg-orange-200/70'
              : f.severity === 'medium'
                ? 'bg-amber-200/70'
                : 'bg-cyan-200/60',
        )}
      >
        {body.slice(f.span_start, f.span_end)}
      </mark>,
    )
    cursor = f.span_end
  })
  nodes.push(body.slice(cursor))
  return <>{nodes}</>
}
