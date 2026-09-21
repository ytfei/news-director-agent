import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Badge, Button, ErrorState, Spinner, cn } from '../components/ui'
import { api, type AvailableConnector, type ConfigField, type ProbeResult, type SyncStats } from '../lib/api'
import { formatDateTime } from '../lib/format'

/**
 * 数据源管理。
 *
 * ★ 关键设计：这一页**不认识任何具体连接器**。
 * 表单由连接器的能力声明（`capability.config_schema`）动态渲染 ——
 * 后端新增一个数据源（RSS / 公众号 / 交易所），这里不用改一行代码。
 * 这兑现了页面上一直写着但此前没落实的那句"表单由能力声明动态渲染"。
 */
export function Connectors() {
  const qc = useQueryClient()
  const [key, setKey] = useState('')
  const [newConfig, setNewConfig] = useState<Record<string, unknown>>({})
  const [validateMsg, setValidateMsg] = useState<Record<string, string>>({})
  const [syncMsg, setSyncMsg] = useState<Record<string, SyncStats | { error: string }>>({})
  const [editing, setEditing] = useState<string | null>(null)
  const [editConfig, setEditConfig] = useState<Record<string, unknown>>({})

  const available = useQuery({ queryKey: ['connectors-available'], queryFn: api.availableConnectors })
  const list = useQuery({ queryKey: ['connectors'], queryFn: api.listConnectors })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['connectors'] })
    qc.invalidateQueries({ queryKey: ['news'] })
  }

  // 默认选中第一个可用连接器（优先快讯），并把 schema 里的默认值填进表单
  useEffect(() => {
    if (key || !available.data?.length) return
    const preferred = available.data.find((c) => c.key.startsWith('tushare.flash')) ?? available.data[0]
    setKey(preferred.key)
    setNewConfig(defaultsOf(preferred))
  }, [available.data, key])

  const create = useMutation({
    mutationFn: () => api.createConnector(key, newConfig),
    onSuccess: () => {
      setNewConfig(key ? defaultsOf(available.data?.find((c) => c.key === key)) : {})
      invalidate()
    },
  })
  const patch = useMutation({
    mutationFn: (id: string) => api.patchConnector(id, { config: editConfig }),
    onSuccess: () => {
      setEditing(null)
      invalidate()
    },
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

  const currentSchema = available.data?.find((c) => c.key === key)?.capability.config_schema ?? []

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-4xl space-y-5">
        <header>
          <h1 className="text-lg font-semibold text-slate-900">数据源管理</h1>
          <p className="mt-0.5 text-xs text-slate-500">
            新增数据源 = 后端加一个文件 + <code className="kbd">@register</code>；下面的表单由连接的**能力声明**动态渲染，
            前端不认识任何具体渠道。
          </p>
        </header>

        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-2 text-sm font-medium text-slate-800">新增数据源</h2>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={key}
              onChange={(e) => {
                const next = e.target.value
                setKey(next)
                setNewConfig(defaultsOf(available.data?.find((c) => c.key === next)))
              }}
              className="h-8 rounded-md border border-slate-300 bg-white px-2 text-xs"
            >
              {(available.data ?? []).map((c) => (
                <option key={c.key} value={c.key}>
                  {c.name}（{c.key}）
                </option>
              ))}
            </select>
            <Button variant="primary" size="sm" onClick={() => create.mutate()} disabled={create.isPending || !key}>
              {create.isPending ? '创建中…' : '创建'}
            </Button>
            {create.error && <span className="text-xs text-rose-600">{(create.error as Error).message}</span>}
          </div>

          {currentSchema.length > 0 && (
            <div className="mt-3 border-t border-slate-100 pt-3">
              <ConfigForm fields={currentSchema} value={newConfig} onChange={setNewConfig} />
            </div>
          )}
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
            const probeEntries = Object.entries(probe)
            const failed = probeEntries.filter(([, r]) => !r.ok)
            const msg = validateMsg[c.id]
            const syncResult = syncMsg[c.id]
            const schema = c.capability.config_schema ?? []
            const isEditing = editing === c.id

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
                  {c.capability.emits_metrics && (
                    <Badge className="bg-cyan-50 text-cyan-700">产出数值事实</Badge>
                  )}
                  {c.consecutive_failures > 0 && (
                    <Badge className="bg-rose-50 text-rose-600">连续失败 {c.consecutive_failures}</Badge>
                  )}

                  <div className="ml-auto flex flex-wrap items-center gap-1.5">
                    {schema.length > 0 && (
                      <Button
                        size="sm"
                        onClick={() => {
                          setEditing(isEditing ? null : c.id)
                          setEditConfig({ ...defaultsOf(undefined, schema), ...(c.config ?? {}) })
                        }}
                      >
                        {isEditing ? '收起配置' : '配置'}
                      </Button>
                    )}
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

                {/* 老 key 的迁移提示：只提示，不自动改数据 */}
                {c.key_migrated_to && (
                  <div className="mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-800">
                    ⚠️ {c.migration_note}（当前仍按 <code>{c.key_migrated_to}</code> 运行）
                  </div>
                )}

                {c.last_error && (
                  <div className="mt-2 rounded border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-700">
                    {c.last_error}
                  </div>
                )}

                {/* 配置编辑：同样由能力声明渲染 */}
                {isEditing && (
                  <div className="mt-3 rounded border border-indigo-200 bg-indigo-50/40 p-3">
                    <ConfigForm fields={schema} value={editConfig} onChange={setEditConfig} />
                    <div className="mt-3 flex gap-2">
                      <Button
                        size="sm"
                        variant="primary"
                        disabled={patch.isPending}
                        onClick={() => patch.mutate(c.id)}
                      >
                        {patch.isPending ? '保存中…' : '保存配置'}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>
                        取消
                      </Button>
                      <span className="self-center text-[11px] text-slate-500">
                        保存后建议点一次「校验」确认配置生效
                      </span>
                    </div>
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
                        {(syncResult as SyncStats).status} · 抓取 {(syncResult as SyncStats).fetched ?? 0} · 新增{' '}
                        {(syncResult as SyncStats).inserted ?? 0} · 重复 {(syncResult as SyncStats).duplicated ?? 0}
                        {!!(syncResult as SyncStats).facts_written &&
                          ` · 数值事实 ${(syncResult as SyncStats).facts_written}`}
                        {(syncResult as SyncStats).empty_reason && ` · ${(syncResult as SyncStats).empty_reason}`}
                      </span>
                    )}
                  </div>
                )}

                {/* 逐来源/逐接口的可用状态（不是笼统的"无权限"） */}
                {probeEntries.length > 0 && (
                  <div className="mt-3">
                    <div className="mb-1 text-[11px] font-medium text-slate-500">
                      可用状态 · {probeEntries.length - failed.length}/{probeEntries.length}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {probeEntries.map(([name, r]) => (
                        <Badge
                          key={name}
                          title={r.reason || `${r.rows} 条`}
                          className={r.ok ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}
                        >
                          {r.label ?? name} {r.ok ? `✓ ${r.rows}` : '✕ 无数据/无权限'}
                        </Badge>
                      ))}
                    </div>
                    {failed.length > 0 && (
                      <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-[11px] text-slate-500">
                        {failed.map(([name, r]) => (
                          <li key={name}>
                            <b>{r.label ?? name}</b>：{r.reason || '无数据'}
                          </li>
                        ))}
                      </ul>
                    )}
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

/** 用声明的默认值初始化表单（含"无默认值"的类型各自的空值）。 */
function defaultsOf(connector?: AvailableConnector, schema?: ConfigField[]): Record<string, unknown> {
  const fields = schema ?? connector?.capability.config_schema ?? []
  const out: Record<string, unknown> = {}
  for (const f of fields) {
    if (f.default !== undefined && f.default !== null) out[f.key] = f.default
    else if (f.type === 'multiselect') out[f.key] = []
    else if (f.type === 'boolean') out[f.key] = false
    else if (f.type === 'number') out[f.key] = 0
    else out[f.key] = ''
  }
  return out
}

function ConfigForm({
  fields,
  value,
  onChange,
}: {
  fields: ConfigField[]
  value: Record<string, unknown>
  onChange: (v: Record<string, unknown>) => void
}) {
  const set = (k: string, v: unknown) => onChange({ ...value, [k]: v })

  return (
    <div className="space-y-3">
      {fields.map((f) => {
        const raw = value[f.key]
        const label = (
          <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
            <b className="text-slate-700">{f.label}</b>
            {f.required && <Badge className="bg-rose-50 text-rose-600">必填</Badge>}
            {f.help && <span className="text-slate-400">{f.help}</span>}
          </div>
        )

        if (f.type === 'multiselect') {
          const picked = Array.isArray(raw) ? (raw as string[]) : []
          return (
            <div key={f.key}>
              {label}
              <div className="flex flex-wrap gap-1.5">
                {f.options.map((o) => {
                  const on = picked.includes(o.value)
                  return (
                    <button
                      key={o.value}
                      type="button"
                      onClick={() =>
                        set(f.key, on ? picked.filter((x) => x !== o.value) : [...picked, o.value])
                      }
                      className={cn(
                        'rounded-full border px-2 py-0.5 text-xs transition-colors',
                        on
                          ? 'border-indigo-400 bg-indigo-50 font-medium text-indigo-700'
                          : 'border-slate-300 bg-white text-slate-600 hover:border-slate-400',
                      )}
                    >
                      {o.label}
                    </button>
                  )
                })}
              </div>
              <div className="mt-1 text-[11px] text-slate-400">已选 {picked.length} 项</div>
            </div>
          )
        }

        if (f.type === 'select') {
          return (
            <div key={f.key}>
              {label}
              <select
                value={typeof raw === 'string' ? raw : ''}
                onChange={(e) => set(f.key, e.target.value)}
                className="h-8 rounded border border-slate-300 bg-white px-2 text-xs"
              >
                <option value="">—</option>
                {f.options.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          )
        }

        if (f.type === 'boolean') {
          return (
            <label key={f.key} className="flex items-center gap-2 text-xs text-slate-700">
              <input
                type="checkbox"
                checked={raw === true}
                onChange={(e) => set(f.key, e.target.checked)}
              />
              {f.label}
              {f.help && <span className="text-[11px] text-slate-400">{f.help}</span>}
            </label>
          )
        }

        return (
          <div key={f.key}>
            {label}
            <input
              type={f.type === 'number' ? 'number' : 'text'}
              value={typeof raw === 'number' || typeof raw === 'string' ? String(raw) : ''}
              onChange={(e) => set(f.key, f.type === 'number' ? Number(e.target.value) : e.target.value)}
              className="h-8 w-full max-w-md rounded border border-slate-300 px-2 text-xs outline-none focus:border-indigo-500"
            />
          </div>
        )
      })}
    </div>
  )
}
