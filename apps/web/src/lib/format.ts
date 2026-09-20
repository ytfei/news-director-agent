/** 展示层格式化工具。后端一律 UTC，展示转本地。 */

/** 素材的「当天分组」键（YYYY-MM-DD，本地时区）。 */
export function todayISO(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const min = Math.floor(diffMs / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  const hour = Math.floor(min / 60)
  if (hour < 24) return `${hour} 小时前`
  const day = Math.floor(hour / 24)
  if (day < 7) return `${day} 天前`
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleString('zh-CN', { hour12: false, timeZoneName: undefined })
}

const CONTENT_TYPE_LABEL: Record<string, string> = {
  flash: '快讯',
  article: '长文',
  announcement: '公告',
  policy: '政策',
  research_report: '研报',
  interactive_qa: '互动问答',
  social_post: '社媒',
  market_data: '行情',
}

export function contentTypeLabel(t: string): string {
  return CONTENT_TYPE_LABEL[t] ?? t
}

const INDUSTRY_LABEL: Record<string, string> = {
  bank: '银行',
  semiconductor: '半导体',
  new_energy: '新能源',
  auto: '汽车',
  real_estate: '地产',
  macro: '宏观',
}

export function industryLabel(t: string): string {
  return INDUSTRY_LABEL[t] ?? t
}

/** 重要度映射为三档徽标（避免用户被信息量淹没，见 docs/03 步骤②） */
export function importanceTier(v: number | null): { label: string; cls: string } {
  if (v === null) return { label: '参考', cls: 'bg-slate-100 text-slate-500' }
  if (v >= 0.7) return { label: '重要', cls: 'bg-rose-100 text-rose-700' }
  if (v >= 0.45) return { label: '一般', cls: 'bg-slate-100 text-slate-600' }
  return { label: '参考', cls: 'bg-slate-100 text-slate-400' }
}
