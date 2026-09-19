import { NavLink, Route, Routes } from 'react-router-dom'
import { cn } from './components/ui'
import { Connectors } from './routes/Connectors'
import { NewsFeed } from './routes/NewsFeed'
import { NewsPage } from './routes/NewsPage'

const NAV = [
  { to: '/', label: '今日收件箱', icon: '📥', end: true },
  { to: '/news', label: '资讯流', icon: '📰', end: false },
  { to: '/settings/connectors', label: '数据源', icon: '🔌', end: false },
]

export default function App() {
  return (
    <div className="flex h-full">
      <nav className="flex w-52 shrink-0 flex-col border-r border-slate-200 bg-white">
        <div className="px-4 py-4">
          <div className="text-sm font-semibold text-slate-900">主理人 Agent</div>
          <div className="mt-0.5 text-[11px] text-slate-400">观点驱动的内容工作台</div>
        </div>
        <div className="flex-1 space-y-0.5 px-2">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] transition-colors',
                  isActive
                    ? 'bg-indigo-50 font-medium text-indigo-700'
                    : 'text-slate-600 hover:bg-slate-50',
                )
              }
            >
              <span>{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </div>
        <div className="border-t border-slate-200 px-4 py-3 text-[11px] text-slate-400">
          M1 · 数据底座
          <div className="mt-1">观点室 / 写作台 · M2/M3</div>
        </div>
      </nav>

      <main className="min-w-0 flex-1">
        <Routes>
          <Route path="/" element={<NewsFeed mode="inbox" />} />
          <Route path="/news" element={<NewsFeed mode="feed" />} />
          <Route path="/news/:id" element={<NewsPage />} />
          <Route path="/settings/connectors" element={<Connectors />} />
          <Route
            path="*"
            element={
              <div className="p-10 text-sm text-slate-500">页面不存在</div>
            }
          />
        </Routes>
      </main>
    </div>
  )
}
