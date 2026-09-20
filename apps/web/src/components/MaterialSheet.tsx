import { useState } from 'react'
import type { Topic } from '../lib/api'
import { todayISO } from '../lib/format'
import { useCreateTopic, useMarkMaterial, usePatchMaterial } from '../hooks/useWorkspace'
import { Badge, Button, cn } from './ui'

const SCORES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

/**
 * 素材标记面板（资讯中心内联，不跳页 —— docs/06 §1 R2/R3）。
 *
 * 三个维度即素材的全部语义：评分（多想写）、主题（多维标签）、日期（默认当天一批）。
 */
export function MaterialSheet({
  newsId,
  material,
  topics,
  onClose,
}: {
  newsId: string
  material?: { id: string; score: number; topics: string[]; material_date: string } | null
  topics: Topic[]
  onClose: () => void
}) {
  const [score, setScore] = useState(material?.score ?? 7)
  const [picked, setPicked] = useState<string[]>(material?.topics ?? [])
  const [date, setDate] = useState(material?.material_date ?? todayISO())
  const [draftTopic, setDraftTopic] = useState('')

  const mark = useMarkMaterial()
  const patch = usePatchMaterial()
  const createTopic = useCreateTopic()
  const pending = mark.isPending || patch.isPending

  const toggle = (name: string) =>
    setPicked((s) => (s.includes(name) ? s.filter((x) => x !== name) : [...s, name]))

  const save = () => {
    const payload = { score, topics: picked, material_date: date }
    const done = () => onClose()
    if (material) patch.mutate({ id: material.id, ...payload }, { onSuccess: done })
    else mark.mutate({ news_id: newsId, ...payload }, { onSuccess: done })
  }

  const addTopic = () => {
    const name = draftTopic.trim()
    if (!name) return
    createTopic.mutate(name, {
      onSuccess: () => {
        setPicked((s) => (s.includes(name) ? s : [...s, name]))
        setDraftTopic('')
      },
    })
  }

  return (
    <div className="mt-2 rounded-lg border border-indigo-200 bg-indigo-50/40 p-3">
      <div className="mb-2 text-[11px] text-slate-500">
        <b className="text-slate-700">标记为素材</b> · 默认归入「{todayISO()}」这一天，可改。素材是点评与选题的唯一原料。
      </div>

      <div className="mb-3">
        <div className="mb-1 text-[11px] text-slate-500">评分（1~10，越高越想写）</div>
        <div className="flex flex-wrap gap-1">
          {SCORES.map((n) => (
            <button
              key={n}
              onClick={() => setScore(n)}
              className={cn(
                'h-7 w-8 rounded border text-xs transition-colors',
                score === n
                  ? 'border-indigo-600 bg-indigo-600 font-medium text-white'
                  : 'border-slate-300 bg-white text-slate-600 hover:border-slate-400',
              )}
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-3">
        <div className="mb-1 text-[11px] text-slate-500">主题（可多选，类似标签）</div>
        <div className="flex flex-wrap gap-1">
          {topics.map((t) => (
            <button
              key={t.id}
              onClick={() => toggle(t.name)}
              className={cn(
                'rounded-full border px-2 py-0.5 text-xs transition-colors',
                picked.includes(t.name)
                  ? 'border-indigo-400 bg-white font-medium text-indigo-700'
                  : 'border-slate-300 bg-white text-slate-600 hover:border-slate-400',
              )}
            >
              {t.name}
            </button>
          ))}
        </div>
        <div className="mt-2 flex items-center gap-2">
          <input
            value={draftTopic}
            onChange={(e) => setDraftTopic(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addTopic()}
            placeholder="新建主题…"
            className="h-7 w-40 rounded border border-slate-300 bg-white px-2 text-xs outline-none focus:border-indigo-500"
          />
          <Button size="sm" variant="ghost" onClick={addTopic} disabled={createTopic.isPending}>
            + 新建
          </Button>
        </div>
      </div>

      <div className="mb-3">
        <div className="mb-1 text-[11px] text-slate-500">归入日期</div>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="h-7 rounded border border-slate-300 bg-white px-2 text-xs outline-none focus:border-indigo-500"
        />
      </div>

      <div className="flex items-center gap-2">
        <Button size="sm" variant="primary" onClick={save} disabled={pending}>
          {pending ? '保存中…' : material ? '保存修改' : '加入素材'}
        </Button>
        <Button size="sm" variant="ghost" onClick={onClose}>
          取消
        </Button>
        {material && <Badge className="bg-white text-slate-500">已在素材库</Badge>}
      </div>
    </div>
  )
}
