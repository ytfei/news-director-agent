import { useEffect, useRef, useState } from 'react'
import type { AnnotationStatus, Verdict } from '../lib/api'
import { useCheckAnnotations, useSaveAnnotation } from '../hooks/useWorkspace'
import { Badge, Button, cn } from './ui'

const STATUS_LABEL: Record<AnnotationStatus, { text: string; cls: string }> = {
  draft: { text: '草稿', cls: 'bg-slate-100 text-slate-500' },
  checking: { text: '检查中', cls: 'bg-slate-100 text-slate-500' },
  needs_revision: { text: '需修改', cls: 'bg-amber-50 text-amber-700' },
  passed: { text: '通过', cls: 'bg-emerald-50 text-emerald-700' },
  blocked: { text: '有红线', cls: 'bg-rose-50 text-rose-700' },
  locked: { text: '已锁定', cls: 'bg-indigo-50 text-indigo-700' },
}

/**
 * 就地批注框（资讯中心内联）。
 *
 * 两个产品约束：
 * 1. 自动保存 —— 主理人是"边刷边记"，任何"记得点保存"的设计都会丢观点；
 * 2. 批注必须挂在素材上 —— 没有素材时由调用方先静默建素材（点评是素材的附属物）。
 */
export function AnnotationBox({
  materialId,
  initialBody,
  versionNo = 0,
  status,
  verdict,
  onClose,
  onJumpReview,
}: {
  materialId: string
  initialBody: string
  versionNo?: number
  status?: AnnotationStatus
  verdict?: Verdict | null
  onClose: () => void
  onJumpReview?: () => void
}) {
  const [body, setBody] = useState(initialBody)
  const [savedAt, setSavedAt] = useState<string | null>(null)
  const dirty = useRef(false)

  const save = useSaveAnnotation()
  const check = useCheckAnnotations()

  // 3s 防抖对齐 docs/03 步骤⑤；这里取 800ms，原型里"已保存"的反馈更即时
  useEffect(() => {
    if (!dirty.current) return
    const t = setTimeout(() => {
      save.mutate(
        { materialId, body },
        { onSuccess: () => setSavedAt(new Date().toLocaleTimeString('zh-CN', { hour12: false }).slice(0, 5)) },
      )
    }, 800)
    return () => clearTimeout(t)
  }, [body, materialId, save])

  const submit = () => {
    save.mutate(
      { materialId, body },
      {
        onSuccess: () => check.mutate([materialId], { onSuccess: () => onJumpReview?.() }),
      },
    )
  }

  const st = status ? STATUS_LABEL[status] : null

  return (
    <div className="mt-2 rounded-lg border border-slate-300 bg-slate-50/60 p-3">
      <div className="mb-1.5 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
        <b className="text-slate-700">我的批注</b>
        <span>不是复述新闻，是「你怎么看」——一句也行</span>
        {st && <Badge className={st.cls}>{st.text}</Badge>}
        {verdict === 'blocked' && <Badge className="bg-rose-50 text-rose-700">存在未处置红线</Badge>}
        <div className="ml-auto flex items-center gap-2">
          {save.isPending ? (
            <span>保存中…</span>
          ) : savedAt ? (
            <span>已保存 · {savedAt}</span>
          ) : versionNo > 0 ? (
            <span>版本 v{versionNo}</span>
          ) : null}
        </div>
      </div>

      <textarea
        value={body}
        onChange={(e) => {
          dirty.current = true
          setBody(e.target.value)
        }}
        rows={4}
        placeholder="写下你的判断…（自动保存）"
        className="w-full resize-y rounded border border-slate-300 bg-white p-2 text-[13px] leading-6 outline-none focus:border-indigo-500"
      />

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Button size="sm" variant="primary" onClick={submit} disabled={check.isPending || !body.trim()}>
          {check.isPending ? '检查中…' : '提交检查'}
        </Button>
        <span className="text-[11px] text-slate-400">
          三轨并行：事实 / 逻辑 / 合规。有红线时不能进入写作。
        </span>
        <div className="ml-auto flex gap-2">
          <Button size="sm" variant="ghost" onClick={onJumpReview} disabled={!versionNo}>
            去体检报告 →
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className={cn(check.isPending && 'opacity-50')}
            onClick={onClose}
          >
            收起
          </Button>
        </div>
      </div>
    </div>
  )
}
