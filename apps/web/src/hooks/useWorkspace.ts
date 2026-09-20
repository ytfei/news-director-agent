import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { toast } from '../components/Toast'

/**
 * 素材 / 批注 / 检查 的写操作。
 *
 * 统一在 mutation 成功后失效「资讯 + 素材 + 统计」三处缓存：
 * 资讯列表带素材徽标，素材视图带批注徽标，统计驱动侧栏，三者必须一起刷新。
 */
function useInvalidateWorkspace() {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: ['news'] })
    qc.invalidateQueries({ queryKey: ['materials'] })
    qc.invalidateQueries({ queryKey: ['material-stats'] })
    qc.invalidateQueries({ queryKey: ['reports'] })
    qc.invalidateQueries({ queryKey: ['projects'] })
  }
}

export function useTopics() {
  return useQuery({ queryKey: ['topics'], queryFn: () => api.listTopics(), staleTime: 5 * 60_000 })
}

export function useMaterialStats(date?: string) {
  return useQuery({
    queryKey: ['material-stats', date ?? 'today'],
    queryFn: () => api.materialStats(date),
  })
}

export function useCreateTopic() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => api.createTopic(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['topics'] }),
    onError: (e: Error) => toast(`新建主题失败：${e.message}`),
  })
}

export function useMarkMaterial() {
  const invalidate = useInvalidateWorkspace()
  return useMutation({
    mutationFn: api.markMaterial,
    onSuccess: (res) => {
      toast(res.created ? `已加入素材 · 评分 ${res.material.score}` : `素材已更新 · 评分 ${res.material.score}`)
      invalidate()
    },
    onError: (e: Error) => toast(`加入素材失败：${e.message}`),
  })
}

export function usePatchMaterial() {
  const invalidate = useInvalidateWorkspace()
  return useMutation({
    mutationFn: (p: { id: string; score?: number; topics?: string[]; material_date?: string }) =>
      api.patchMaterial(p.id, { score: p.score, topics: p.topics, material_date: p.material_date }),
    onSuccess: () => {
      toast('素材已更新')
      invalidate()
    },
    onError: (e: Error) => toast(`更新失败：${e.message}`),
  })
}

export function useDeleteMaterial() {
  const invalidate = useInvalidateWorkspace()
  return useMutation({
    mutationFn: (id: string) => api.deleteMaterial(id),
    onSuccess: () => {
      toast('已移出素材库')
      invalidate()
    },
  })
}

export function useSaveAnnotation() {
  const invalidate = useInvalidateWorkspace()
  return useMutation({
    mutationFn: (p: { materialId: string; body: string }) => api.putAnnotation(p.materialId, p.body),
    onSuccess: () => invalidate(),
    onError: (e: Error) => toast(`保存批注失败：${e.message}`),
  })
}

export function useCheckAnnotations() {
  const invalidate = useInvalidateWorkspace()
  return useMutation({
    mutationFn: (materialIds: string[]) => api.checkAnnotations(materialIds),
    onSuccess: (res) => {
      const s = res.verdict_summary
      toast(
        `检查完成 · 通过 ${s.passed ?? 0} / 需修改 ${s.needs_revision ?? 0} / 红线 ${s.blocked ?? 0}`,
      )
      invalidate()
    },
    onError: (e: Error) => toast(`检查失败：${e.message}`),
  })
}

export function useResolveFinding() {
  const qc = useQueryClient()
  const invalidate = useInvalidateWorkspace()
  return useMutation({
    mutationFn: (p: { findingId: string; action: 'accepted' | 'dismissed' | 'ignored'; reason?: string }) =>
      api.resolveFinding(p.findingId, p.action, p.reason),
    onSuccess: (res, vars) => {
      if (vars.action === 'accepted') {
        toast(res.needs_recheck ? '已采纳建议 · 正文已改写，建议复检' : '已采纳')
      } else if (vars.action === 'dismissed') {
        toast('已驳回 · 同一问题不再重复报')
      } else {
        toast('已忽略')
      }
      qc.invalidateQueries({ queryKey: ['report'] })
      invalidate()
    },
    onError: (e: Error) => toast(`处置失败：${e.message}`),
  })
}
