import { useEffect } from 'react'

interface Options {
  count: number
  cursor: number
  setCursor: (n: number) => void
  onStar: () => void
  onRate: (n: number) => void
  onToggleSelect: () => void
  /** 抽屉打开或输入框聚焦时应禁用 */
  enabled: boolean
}

/** 全键盘操作：j/k 移动、s 收藏、1~5 评级、space 选中（docs/03 步骤②）。 */
export function useKeyboardNav({
  count,
  cursor,
  setCursor,
  onStar,
  onRate,
  onToggleSelect,
  enabled,
}: Options) {
  useEffect(() => {
    if (!enabled) return

    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return
      if (e.metaKey || e.ctrlKey || e.altKey) return

      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault()
        setCursor(Math.min(cursor + 1, count - 1))
      } else if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault()
        setCursor(Math.max(cursor - 1, 0))
      } else if (e.key === 's') {
        e.preventDefault()
        onStar()
      } else if (e.key === ' ') {
        e.preventDefault()
        onToggleSelect()
      } else if (/^[1-5]$/.test(e.key)) {
        e.preventDefault()
        onRate(Number(e.key))
      }
    }

    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [count, cursor, setCursor, onStar, onRate, onToggleSelect, enabled])
}
