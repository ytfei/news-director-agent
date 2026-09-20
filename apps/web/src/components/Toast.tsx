import { useEffect, useState } from 'react'

type Listener = (message: string) => void
const listeners = new Set<Listener>()

/** 全局轻提示：任何模块都能调用，避免为一次提示引入 Provider 层级。 */
export function toast(message: string) {
  listeners.forEach((l) => l(message))
}

export function Toaster() {
  const [msg, setMsg] = useState<string | null>(null)

  useEffect(() => {
    const l: Listener = (m) => setMsg(m)
    listeners.add(l)
    return () => {
      listeners.delete(l)
    }
  }, [])

  useEffect(() => {
    if (!msg) return
    const t = setTimeout(() => setMsg(null), 2400)
    return () => clearTimeout(t)
  }, [msg])

  if (!msg) return null
  return (
    <div
      onClick={() => setMsg(null)}
      className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 cursor-pointer rounded-full bg-slate-900 px-4 py-2 text-xs text-white shadow-lg"
    >
      {msg}
    </div>
  )
}
