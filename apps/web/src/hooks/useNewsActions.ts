import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type NewsItem } from '../lib/api'

/** 收藏 / 评级：乐观更新，失败回滚 + 提示（docs/04 §8.4）。 */
export function useNewsActions() {
  const qc = useQueryClient()
  const [starred, setStarred] = useState<Set<string>>(new Set())
  const [ratings, setRatings] = useState<Record<string, number>>({})
  const [toast, setToast] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: (p: { id: string; action: 'star' | 'unstar' | 'rate'; rating?: number }) =>
      api.createAction(p.id, p.action, p.rating),
    onSuccess: (_res, vars) => {
      if (vars.action === 'rate' && vars.rating) {
        setRatings((s) => ({ ...s, [vars.id]: vars.rating! }))
        setToast(`已评级 ${vars.rating}★`)
      }
    },
    onError: (_e, vars) => {
      // 回滚乐观更新
      if (vars.action === 'star') setStarred((s) => new Set([...s].filter((x) => x !== vars.id)))
      if (vars.action === 'unstar') setStarred((s) => new Set(s).add(vars.id))
      setToast('操作失败，已回滚')
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['news'] }),
  })

  const toggleStar = (item: NewsItem) => {
    const next = !starred.has(item.id)
    setStarred((s) => {
      const n = new Set(s)
      next ? n.add(item.id) : n.delete(item.id)
      return n
    })
    mutation.mutate({ id: item.id, action: next ? 'star' : 'unstar' })
  }

  const rate = (item: NewsItem, rating: number) => {
    setRatings((s) => ({ ...s, [item.id]: rating }))
    mutation.mutate({ id: item.id, action: 'rate', rating })
  }

  return { starred, ratings, toggleStar, rate, toast, clearToast: () => setToast(null) }
}
