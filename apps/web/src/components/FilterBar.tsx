import type { ContentType } from '../lib/api'
import { Button, cn } from './ui'

export type TimeRange = 'today' | '3d' | 'week' | 'all'

const RANGES: { key: TimeRange; label: string }[] = [
  { key: 'today', label: '今日' },
  { key: '3d', label: '3 天' },
  { key: 'week', label: '本周' },
  { key: 'all', label: '全部' },
]

const TYPES: { key: ContentType | ''; label: string }[] = [
  { key: '', label: '全部类型' },
  { key: 'flash', label: '快讯' },
  { key: 'article', label: '长文' },
  { key: 'announcement', label: '公告' },
  { key: 'policy', label: '政策' },
  { key: 'research_report', label: '研报' },
]

const INDUSTRIES: { key: string; label: string }[] = [
  { key: '', label: '全部行业' },
  { key: 'macro', label: '宏观' },
  { key: 'bank', label: '银行' },
  { key: 'semiconductor', label: '半导体' },
  { key: 'new_energy', label: '新能源' },
  { key: 'auto', label: '汽车' },
  { key: 'real_estate', label: '地产' },
]

export interface Filters {
  range: TimeRange
  content_type: ContentType | ''
  industry: string
}

export function rangeToSince(r: TimeRange): string | undefined {
  const now = new Date()
  const ms = { today: 1, '3d': 3, week: 7, all: 0 }[r] * 86400_000
  return ms ? new Date(now.getTime() - ms).toISOString() : undefined
}

export function FilterBar({
  value,
  onChange,
  resultCount,
  loading,
}: {
  value: Filters
  onChange: (f: Filters) => void
  resultCount: number
  loading: boolean
}) {
  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => onChange({ ...value, [k]: v })

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-white px-4 py-2.5">
      <div className="flex overflow-hidden rounded-md border border-slate-300">
        {RANGES.map((r) => (
          <button
            key={r.key}
            onClick={() => set('range', r.key)}
            className={cn(
              'px-2.5 py-1 text-xs transition-colors',
              value.range === r.key
                ? 'bg-indigo-600 text-white'
                : 'bg-white text-slate-600 hover:bg-slate-50',
            )}
          >
            {r.label}
          </button>
        ))}
      </div>

      <select
        value={value.content_type}
        onChange={(e) => set('content_type', e.target.value as ContentType | '')}
        className="h-7 rounded-md border border-slate-300 bg-white px-2 text-xs text-slate-700"
      >
        {TYPES.map((t) => (
          <option key={t.key} value={t.key}>
            {t.label}
          </option>
        ))}
      </select>

      <select
        value={value.industry}
        onChange={(e) => set('industry', e.target.value)}
        className="h-7 rounded-md border border-slate-300 bg-white px-2 text-xs text-slate-700"
      >
        {INDUSTRIES.map((i) => (
          <option key={i.key} value={i.key}>
            {i.label}
          </option>
        ))}
      </select>

      <div className="ml-auto flex items-center gap-2 text-xs text-slate-500">
        {loading ? '加载中…' : `${resultCount} 条`}
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onChange({ range: 'all', content_type: '', industry: '' })}
        >
          重置
        </Button>
      </div>
    </div>
  )
}
