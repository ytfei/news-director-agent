import { Link, Route, Routes, useLocation } from 'react-router-dom'
import { Toaster } from './components/Toast'
import { cn } from './components/ui'
import { Compose } from './routes/Compose'
import { Connectors } from './routes/Connectors'
import { Inbox } from './routes/Inbox'
import { NewsCenter } from './routes/NewsCenter'
import { NewsPage } from './routes/NewsPage'
import { Projects } from './routes/Projects'
import { Prompts } from './routes/Prompts'
import { Review } from './routes/Review'
import { Workbench } from './routes/Workbench'

interface NavItem {
  to: string
  label: string
  icon: string
  /** 需要匹配的查询串（用于同路径不同视图） */
  search?: string
}

const NAV: { group: string; level?: string; items: NavItem[] }[] = [
  {
    group: '第一层 · 资讯台',
    level: 'L1',
    items: [
      { to: '/', label: '今日收件箱', icon: '📥' },
      { to: '/news', label: '资讯中心', icon: '📰' },
      { to: '/news?view=material', label: '素材库', icon: '🔖', search: '?view=material' },
    ],
  },
  {
    group: '第二层 · 观点室',
    level: 'L2',
    items: [
      { to: '/workbench', label: '点评工作台', icon: '✍️' },
      { to: '/reviews', label: 'AI 体检报告', icon: '🛡️' },
    ],
  },
  {
    group: '第三层 · 写作台',
    level: 'L3',
    items: [
      { to: '/projects', label: '选题', icon: '📁' },
      { to: '/prompts', label: '提示词', icon: '💬' },
    ],
  },
  { group: '设置', items: [{ to: '/settings/connectors', label: '数据源', icon: '🔌' }] },
]

export default function App() {
  const location = useLocation()

  const isActive = (n: NavItem) => {
    const [path, search] = n.to.split('?')
    if (n.search) return location.pathname === path && location.search === `?${search}`
    if (path === '/news') return location.pathname === '/news' && location.search !== '?view=material'
    if (path === '/projects') return location.pathname.startsWith('/projects')
    return location.pathname === path
  }

  return (
    <div className="flex h-full">
      <nav className="flex w-56 shrink-0 flex-col overflow-y-auto border-r border-slate-200 bg-white">
        <div className="px-4 py-4">
          <div className="text-sm font-semibold text-slate-900">主理人 Agent</div>
          <div className="mt-0.5 text-[11px] text-slate-400">观点驱动的内容工作台</div>
        </div>

        <div className="flex-1 space-y-4 px-2 pb-4">
          {NAV.map((g) => (
            <div key={g.group} className="space-y-0.5">
              <div className="flex items-center gap-1.5 px-2.5 pb-1 text-[10px] uppercase tracking-wide text-slate-400">
                {g.level && (
                  <span className="rounded bg-slate-100 px-1 text-[10px] text-slate-500">{g.level}</span>
                )}
                {g.group}
              </div>
              {g.items.map((n) => (
                <Link
                  key={n.to}
                  to={n.to}
                  className={cn(
                    'flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] transition-colors',
                    isActive(n) ? 'bg-indigo-50 font-medium text-indigo-700' : 'text-slate-600 hover:bg-slate-50',
                  )}
                >
                  <span>{n.icon}</span>
                  {n.label}
                </Link>
              ))}
            </div>
          ))}
        </div>

        <div className="border-t border-slate-200 px-4 py-3 text-[11px] text-slate-400">
          M2 · 素材 → 批注 → 体检 → 选题
          <div className="mt-1">写作台（M3）为占位实现</div>
        </div>
      </nav>

      <main className="min-w-0 flex-1">
        <Routes>
          <Route path="/" element={<Inbox />} />
          <Route path="/news" element={<NewsCenter />} />
          <Route path="/news/:id" element={<NewsPage />} />
          <Route path="/workbench" element={<Workbench />} />
          <Route path="/reviews" element={<Review />} />
          <Route path="/reviews/:reportId" element={<Review />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/projects/:id/compose" element={<Compose />} />
          <Route path="/prompts" element={<Prompts />} />
          <Route path="/settings/connectors" element={<Connectors />} />
          <Route path="*" element={<div className="p-10 text-sm text-slate-500">页面不存在</div>} />
        </Routes>
      </main>

      <Toaster />
    </div>
  )
}
