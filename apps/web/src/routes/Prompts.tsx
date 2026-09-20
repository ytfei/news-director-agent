import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from '../components/Toast'
import { Badge, Button, Spinner } from '../components/ui'
import { api } from '../lib/api'

const CATEGORY: Record<string, { text: string; cls: string }> = {
  style: { text: '风格', cls: 'bg-indigo-50 text-indigo-700' },
  structure: { text: '结构', cls: 'bg-cyan-50 text-cyan-700' },
  persona: { text: '人格', cls: 'bg-violet-50 text-violet-700' },
  taboo: { text: '禁忌', cls: 'bg-rose-50 text-rose-700' },
}

/**
 * 提示词管理。
 *
 * 产品视角：提示词不是一串字符，而是**可版本化、可按需加载进 Agent 的技能包**
 * （`docs/01` §4.2 D）——所以这里按 category 分组，并展示版本号。
 */
export function Prompts() {
  const qc = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ name: '', category: 'style', body: '', description: '' })

  const { data, isLoading } = useQuery({ queryKey: ['prompts'], queryFn: () => api.listPrompts() })
  const prompts = data ?? []

  const create = useMutation({
    mutationFn: () => api.createPrompt(form),
    onSuccess: (p) => {
      toast(`已保存 ${p.name} v${p.version_no}`)
      qc.invalidateQueries({ queryKey: ['prompts'] })
      setCreating(false)
      setForm({ name: '', category: 'style', body: '', description: '' })
    },
    onError: (e: Error) => toast(`保存失败：${e.message}`),
  })

  const groups = ['style', 'structure', 'persona', 'taboo']

  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="mb-4 flex items-center gap-2">
        <h1 className="text-base font-semibold text-slate-900">提示词</h1>
        <span className="text-[11px] text-slate-400">
          人格 + 结构 + 禁忌可叠加；官方模板库开箱可用
        </span>
        <div className="ml-auto">
          <Button size="sm" variant="primary" onClick={() => setCreating((v) => !v)}>
            + 新建提示词
          </Button>
        </div>
      </div>

      {creating && (
        <div className="mb-4 rounded-lg border border-indigo-200 bg-indigo-50/40 p-3">
          <div className="mb-2 flex flex-wrap gap-2">
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="名称，如「我的口头禅与用词偏好」"
              className="h-8 w-64 rounded border border-slate-300 px-2 text-xs outline-none focus:border-indigo-500"
            />
            <select
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
              className="h-8 rounded border border-slate-300 bg-white px-2 text-xs"
            >
              {groups.map((g) => (
                <option key={g} value={g}>
                  {CATEGORY[g].text}
                </option>
              ))}
            </select>
          </div>
          <input
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="一句话说明（可选）"
            className="mb-2 h-8 w-full rounded border border-slate-300 px-2 text-xs outline-none focus:border-indigo-500"
          />
          <textarea
            value={form.body}
            onChange={(e) => setForm({ ...form, body: e.target.value })}
            rows={5}
            placeholder="正文。可用变量：{作者名} {字数} {读者对象}"
            className="w-full rounded border border-slate-300 p-2 font-mono text-xs outline-none focus:border-indigo-500"
          />
          <div className="mt-2 flex gap-2">
            <Button
              size="sm"
              variant="primary"
              disabled={!form.name.trim() || !form.body.trim() || create.isPending}
              onClick={() => create.mutate()}
            >
              {create.isPending ? '保存中…' : '保存为新版本'}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setCreating(false)}>
              取消
            </Button>
          </div>
        </div>
      )}

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Spinner /> 加载中…
        </div>
      )}

      <div className="space-y-4">
        {groups.map((g) => {
          const list = prompts.filter((p) => p.category === g)
          if (!list.length) return null
          return (
            <div key={g} className="rounded-lg border border-slate-200 bg-white">
              <div className="flex items-center gap-2 border-b border-slate-100 px-3 py-2">
                <Badge className={CATEGORY[g].cls}>{CATEGORY[g].text}</Badge>
                <span className="text-xs font-semibold text-slate-700">{list.length} 套</span>
              </div>
              <div className="divide-y divide-slate-100">
                {list.map((p) => (
                  <div key={p.id} className="p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-medium text-slate-800">{p.name}</span>
                      <Badge>v{p.version_no}</Badge>
                      {p.is_official && <Badge className="bg-emerald-50 text-emerald-700">官方模板</Badge>}
                    </div>
                    {p.description && (
                      <div className="mt-1 text-[11px] text-slate-500">{p.description}</div>
                    )}
                    {p.body && (
                      <pre className="mt-2 max-h-28 overflow-y-auto whitespace-pre-wrap rounded bg-slate-50 p-2 font-mono text-[11px] leading-5 text-slate-600">
                        {p.body}
                      </pre>
                    )}
                    {!!p.variables?.length && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {p.variables.map((v) => (
                          <Badge key={v} className="bg-indigo-50 text-indigo-700">
                            {v}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
