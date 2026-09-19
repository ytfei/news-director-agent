import type { ButtonHTMLAttributes, ReactNode } from 'react'

export function cn(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ')
}

export function Badge({
  children,
  className,
  title,
}: {
  children: ReactNode
  className?: string
  title?: string
}) {
  return (
    <span
      title={title}
      className={cn(
        'inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium leading-4',
        className ?? 'bg-slate-100 text-slate-600',
      )}
    >
      {children}
    </span>
  )
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'ghost' | 'danger' | 'outline'
  size?: 'sm' | 'md'
}

export function Button({
  variant = 'outline',
  size = 'md',
  className,
  ...props
}: ButtonProps) {
  const base =
    'inline-flex items-center justify-center gap-1 rounded-md font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50'
  const sizes = { sm: 'h-7 px-2 text-xs', md: 'h-9 px-3 text-sm' }
  const variants = {
    primary: 'bg-indigo-600 text-white hover:bg-indigo-700 border border-indigo-600',
    outline: 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50',
    ghost: 'text-slate-600 hover:bg-slate-100',
    danger: 'border border-rose-200 bg-white text-rose-600 hover:bg-rose-50',
  }
  return <button className={cn(base, sizes[size], variants[variant], className)} {...props} />
}

export function Spinner({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600',
        className,
      )}
    />
  )
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-20 text-center">
      <div className="text-sm font-medium text-slate-500">{title}</div>
      {hint && <div className="max-w-sm text-xs text-slate-400">{hint}</div>}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
      <div className="font-medium">加载失败</div>
      <div className="mt-1 break-words text-xs text-rose-600">{message}</div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 rounded border border-rose-300 px-2 py-1 text-xs hover:bg-rose-100"
        >
          重试
        </button>
      )}
    </div>
  )
}
