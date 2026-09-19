import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Badge, Button, ErrorState, Spinner } from '../components/ui'
import { api, type ProbeResult, type SyncStats } from '../lib/api'
import { formatDateTime } from '../lib/format'

export function Connectors() {
  const qc = useQueryClient()
  const [key, setKey] = useState('tushare.news')
  const [validateMsg, setValidateMsg] = useState<Record<string, string>>({})
  const [syncMsg, setSyncMsg] = useState<Record<string, SyncStats | { error: string }>>({})

  const available = useQuery({ queryKey: ['connectors-available'], queryFn: api.availableConnectors })
  const list = useQuery({ queryKey: ['connectors'], queryFn: api.listConnectors })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['connectors'] })
    qc.invalidateQueries({ queryKey: ['news'] })
  }

  const create = useMutation({
    mutationFn: () => api.createConnector(key),
    onSuccess: invalidate,
  })
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteConnector(id),
    onSuccess: invalidate,
  })

  const validate = async (id: string) => {
    setValidateMsg((s) => ({ ...s, [id]: '校验中…' }))
    try {
      const r = await api.validateConnector(id)
      setValidateMsg((s) => ({ ...s, [id]: `${r.ok ? '✅' : '❌'} ${r.message}` }))
    } catch (e) {
      setValidateMsg((s) => ({ ...s, [id]: `❌ ${(e as Error).message}` }))
    }
    invalidate()
  }

  const sync = async (id: string) => {
    setSyncMsg((s) => ({ ...s, [id]: { error: '同步中…' } as unknown as SyncStats }))
    try {
      const r = await api.syncConnector(id)
      setSyncMsg((s) => ({ ...s, [id]: r }))
    } catch (e) {
      setSyncMsg((s) => ({ ...s, [id]: { error: (e as Error).message } }))
    }
    invalidate()
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-4xl space-y-5">
        <header>
          <h1 className="text-lg font-semibold text-slate-900">数据源管理</h1>
          <p className="mt-0.5 text-xs text-slate-500">
            新增数据源 = 后端加一个文件 + <code className="kbd">@register</code>，此处表单由能力声明动态渲染。
          </p>
        </header>

        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-2 text-sm font-medium text-slate-800">新增数据源</h2>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={key}
              onChange={(e) => setKey(e.target.value)}
              className="h-8 rounded-md border border-slate-300 bg-white px-2 text-xs"
            >
              {(available.data ?? []).map((c) => (
                <option key={c.key} value={c.key}>
                  {c.name}（{c.key}）
                </option>
              ))}
            </select>
            <Button variant="primary" size="sm" onClick={() => create.mutate()} disabled={create.isPending}>
              {create.isPending ? '创建中…' : '创建'}
            </Button>
            {create.error && (
              <span className="text-xs text-rose-600">{(create.error as Error).message}</span>
            )}
          </div>
        </section>

        {list.isLoading && (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> 加载中…
          </div>
        )}
        {list.error && <ErrorState message={(list.error as Error).message} />}

        <div className="space-y-3">
          {(list.data ?? []).map((c) => {
            const probe = (c.config?.probe ?? {}) as Record<string, ProbeResult>
            const hasProbe = Object.keys(probe).length > 0
            const msg = validateMsg[c.id]
            const syncResult = syncMsg[c.id]

            return (
              <section key={c.id} className="rounded-lg border border-slate-200 bg-white p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-slate-900">{c.display_name}</span>
                  <Badge className="bg-slate-100 text-slate-600">{c.key}</Badge>
                  <Badge
                    className={
                      c.status === 'active'
                        ? 'bg-emerald-100 text-emerald-700'
                        : c.status === 'error'
                          ? 'bg-rose-100 text-rose-700'
                          : 'bg-slate-100 text-slate-500'
                    }
                  >
                    {c.status}
                  </Badge>
                  {c.consecutive_failures > 0 && (
                    <Badge className="bg-rose-50 text-rose-600">
                      连续失败 {c.consecutive_failures}
                    </Badge>
                  )}

                  <div className="ml-auto flex flex-wrap items-center gap-1.5">
                    <Button size="sm" onClick={() => validate(c.id)}>
                      校验
                    </Button>
                    <Button size="sm" variant="primary" onClick={() => sync(c.id)}>
                      同步
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() => remove.mutate(c.id)}
                      disabled={remove.isPending}
                    >
                      删除
                    </Button>
                  </div>
                </div>

                <div className="mt-1.5 text-[11px] text-slate-500">
                  上次运行 {formatDateTime(c.last_run_at)} · 下次 {formatDateTime(c.next_run_at)} ·
                  计划 {c.schedule_cron ?? '—'}
                </div>

                {c.last_error && (
                  <div className="mt-2 rounded border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-700">
                    {c.last_error}
                  </div>
                )}
                {msg && (
                  <div className="mt-2 whitespace-pre-wrap rounded bg-slate-50 px-2 py-1.5 text-[11px] text-slate-700">
                    {msg}
                  </div>
                )}

                {syncResult && (
                  <div className="mt-2 rounded bg-slate-50 px-2 py-1.5 text-[11px]">
                    {'error' in syncResult && !('status' in syncResult) ? (
                      <span className="text-rose-600">{syncResult.error}</span>
                    ) : (
                      <span className="text-slate-700">
                        {(syncResult as SyncStats).status} · 抓取{' '}
                        {(syncResult as SyncStats).fetched ?? 0} · 新增{' '}
                        {(syncResult as SyncStats).inserted ?? 0} · 重复{' '}
                        {(syncResult as SyncStats).duplicated ?? 0}
                        {(syncResult as SyncStats).empty_reason &&
                          ` · ${(syncResult as SyncStats).empty_reason}`}
                      </span>
                    )}
                  </div>
                )}

                {/* 权限探测结果：明确告知"当前 token 无 XX 接口权限"（docs/03 步骤①） */}
                {hasProbe && (
                  <div className="mt-3">
                    <div className="mb-1 text-[11px] font-medium text-slate-500">接口权限探测</div>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(probe).map(([name, r]) => (
                        <Badge
                          key={name}
                          title={r.reason}
                          className={
                            r.ok ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'
                          }
                        >
                          {name} {r.ok ? `✓ ${r.rows}` : '✕ 无权限/空'}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </section>
            )
          })}
        </div>
      </div>
    </div>
  )
}
