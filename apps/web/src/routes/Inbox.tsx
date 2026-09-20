import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Badge, Spinner, cn } from '../components/ui'
import { useMaterialStats } from '../hooks/useWorkspace'
import { api } from '../lib/api'
import { todayISO } from '../lib/format'

const STATUS_LABEL: Record<string, string> = {
  collecting: '收集素材',
  reviewing: '检查中',
  ready: '就绪',
  composing: '写作中',
  drafting: '草稿',
  completed: '已完成',
  archived: '归档',
  cancelled: '已取消',
}

/**
 * 今日收件箱。
 *
 * 定位：**一天的入口**，不是资讯列表。只回答三个问题：
 * 今天标了多少素材、哪些还没批注、有没有卡住的红线或选题。
 */
export function Inbox() {
  const today = todayISO()
  const statsQuery = useMaterialStats(today)

  const todoQuery = useQuery({
    queryKey: ['materials', 'inbox-todo'],
    queryFn: () => api.listMaterials({ has_annotation: false, limit: 5 }),
  })
  const annQuery = useQuery({
    queryKey: ['materials', 'inbox-ann'],
    queryFn: () => api.listMaterials({ has_annotation: true, limit: 50 }),
  })
  const projectsQuery = useQuery({ queryKey: ['projects'], queryFn: () => api.listProjects() })

  const stats = statsQuery.data
  const todo = todoQuery.data ?? []
  const blocked = (annQuery.data ?? []).filter((m) => m.annotation?.verdict === 'blocked')
  const projects = projectsQuery.data ?? []
  const activeProjects = projects.filter((p) =>
    ['ready', 'composing', 'drafting', 'reviewing'].includes(p.status),
  )

  return (
    <div className="mx-auto max-w-5xl p-6">
      {/* 头部 */}
      <div className="mb-5 rounded-xl bg-gradient-to-br from-slate-900 via-slate-800 to-indigo-900 p-5 text-white">
        <h1 className="text-lg font-semibold">今天，先挑几条素材</h1>
        <p className="mt-1 max-w-2xl text-[13px] leading-6 text-slate-300">
          这个产品只希望你养成一个习惯：<b className="text-white">对感兴趣的资讯写下判断</b>。
          标记素材（评分 + 主题 + 日期）是入口，批注是加深，剩下的交给系统。
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Link
            to="/news"
            className="rounded-md bg-white px-3 py-1.5 text-xs font-medium text-slate-900 hover:bg-slate-100"
          >
            📰 去资讯中心挑素材
          </Link>
          <Link
            to="/news?view=material"
            className="rounded-md border border-white/25 px-3 py-1.5 text-xs text-slate-200 hover:bg-white/10"
          >
            🔖 看素材库
          </Link>
          <Link
            to="/workbench"
            className="rounded-md border border-white/25 px-3 py-1.5 text-xs text-slate-200 hover:bg-white/10"
          >
            ✍️ 继续批注
          </Link>
        </div>
      </div>

      {/* 今日素材 */}
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="今日素材" value={stats?.total ?? 0} hint={`${today}`} />
        <Stat label="已批注" value={stats?.with_annotation ?? 0} hint="有你的判断" tone="ok" />
        <Stat
          label="待批注"
          value={stats?.without_annotation ?? 0}
          hint="没写也能直接写作"
          tone="warn"
        />
        <Stat label="平均评分" value={stats?.avg_score ?? 0} hint="1~10" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* 待办 */}
        <div className="rounded-lg border border-slate-200 bg-white">
          <div className="border-b border-slate-100 px-3 py-2 text-xs font-semibold text-slate-700">
            待办
          </div>
          <div className="divide-y divide-slate-100">
            <TodoRow
              icon="✍️"
              title="给素材补批注"
              badge={`${stats?.without_annotation ?? 0} 条`}
              badgeCls="bg-indigo-50 text-indigo-700"
              desc="在资讯中心就地写，不用跳页"
              to="/workbench"
            />
            <TodoRow
              icon="🛡️"
              title="处理体检红线"
              badge={blocked.length ? `${blocked.length} 条 blocked` : '无'}
              badgeCls={blocked.length ? 'bg-rose-50 text-rose-700' : 'bg-slate-100 text-slate-400'}
              desc={
                blocked.length
                  ? `${blocked[0].news?.title.slice(0, 24) ?? ''}… 命中合规红线，未处置前不能写作`
                  : '所有批注都没有红线'
              }
              to="/reviews"
            />
            <TodoRow
              icon="📁"
              title="继续选题"
              badge={`${activeProjects.length} 个`}
              badgeCls="bg-emerald-50 text-emerald-700"
              desc={
                activeProjects.length
                  ? activeProjects.map((p) => p.title).join(' / ')
                  : '还没有进行中的选题'
              }
              to="/projects"
            />
          </div>
        </div>

        {/* 待批注素材 */}
        <div className="rounded-lg border border-slate-200 bg-white">
          <div className="flex items-center gap-2 border-b border-slate-100 px-3 py-2">
            <span className="text-xs font-semibold text-slate-700">评分最高、还没批注</span>
            <Link to="/news?view=todo" className="ml-auto text-[11px] text-indigo-600 hover:underline">
              全部 →
            </Link>
          </div>
          <div className="divide-y divide-slate-100">
            {todoQuery.isLoading && (
              <div className="flex items-center gap-2 p-3 text-xs text-slate-500">
                <Spinner /> 加载中…
              </div>
            )}
            {!todoQuery.isLoading && todo.length === 0 && (
              <div className="p-3 text-[11px] text-slate-400">
                没有待批注的素材 —— 要么都写完了，要么还没标素材。
              </div>
            )}
            {todo.map((m) => (
              <Link key={m.id} to="/news?view=todo" className="block p-3 hover:bg-slate-50">
                <div className="flex items-start gap-2">
                  <span className="rounded bg-indigo-600 px-1.5 text-[11px] font-semibold text-white">
                    {m.score}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-xs font-medium text-slate-800">{m.news?.title}</div>
                    <div className="mt-0.5 text-[10px] text-slate-500">
                      {m.news?.source_name} · {m.material_date}
                      {m.topics.length ? ` · ${m.topics.join('/')}` : ''}
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>

      {/* 选题概览 */}
      <div className="mt-4 rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center gap-2 border-b border-slate-100 px-3 py-2">
          <span className="text-xs font-semibold text-slate-700">选题</span>
          <Link to="/projects" className="ml-auto text-[11px] text-indigo-600 hover:underline">
            管理 →
          </Link>
        </div>
        <div className="divide-y divide-slate-100">
          {projectsQuery.isLoading && (
            <div className="flex items-center gap-2 p-3 text-xs text-slate-500">
              <Spinner /> 加载中…
            </div>
          )}
          {!projectsQuery.isLoading && projects.length === 0 && (
            <div className="p-3 text-[11px] text-slate-400">
              还没有选题。素材攒够一组，就可以用它建选题并直接交给 AI。
            </div>
          )}
          {projects.slice(0, 5).map((p) => (
            <Link
              key={p.id}
              to="/projects"
              className="flex items-center gap-2 p-3 hover:bg-slate-50"
            >
              <span className="min-w-0 flex-1 truncate text-xs font-medium text-slate-800">
                {p.title}
              </span>
              <Badge
                className={
                  p.assessment?.with_blocker
                    ? 'bg-rose-50 text-rose-700'
                    : p.status === 'ready'
                      ? 'bg-emerald-50 text-emerald-700'
                      : 'bg-slate-100 text-slate-500'
                }
              >
                {p.assessment?.with_blocker ? '有红线' : STATUS_LABEL[p.status] ?? p.status}
              </Badge>
              <span className="text-[10px] text-slate-500">
                {p.assessment?.materials ?? 0} 素材 / {p.assessment?.with_annotation ?? 0} 批注
              </span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}

function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string
  value: number
  hint?: string
  tone?: 'ok' | 'warn'
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mt-0.5 text-2xl font-bold leading-8 text-slate-900">{value}</div>
      {hint && (
        <div
          className={cn(
            'text-[11px]',
            tone === 'ok' ? 'text-emerald-600' : tone === 'warn' ? 'text-amber-600' : 'text-slate-400',
          )}
        >
          {hint}
        </div>
      )}
    </div>
  )
}

function TodoRow({
  icon,
  title,
  badge,
  badgeCls,
  desc,
  to,
}: {
  icon: string
  title: string
  badge: string
  badgeCls: string
  desc: string
  to: string
}) {
  return (
    <Link to={to} className="block p-3 hover:bg-slate-50">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-slate-800">
          {icon} {title}
        </span>
        <Badge className={cn('ml-auto', badgeCls)}>{badge}</Badge>
      </div>
      <div className="mt-1 line-clamp-2 text-[11px] text-slate-500">{desc}</div>
    </Link>
  )
}
