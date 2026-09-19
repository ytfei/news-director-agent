import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { NewsDetail } from '../components/NewsDetail'
import { ErrorState } from '../components/ui'
import { api } from '../lib/api'

export function NewsPage() {
  const { id } = useParams<{ id: string }>()
  const { data, isLoading, error } = useQuery({
    queryKey: ['news', id],
    queryFn: () => api.getNews(id!),
    enabled: !!id,
  })

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-6 py-6">
        <Link to="/news" className="text-xs text-indigo-600 hover:underline">
          ← 返回资讯流
        </Link>
        <div className="mt-3">
          {error ? (
            <ErrorState message={(error as Error).message} />
          ) : (
            <NewsDetail data={data} loading={isLoading} error={null} />
          )}
        </div>
      </div>
    </div>
  )
}
