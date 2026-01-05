import { useState } from 'react'
import { useStore } from '../store'
import { useWorkers, useDrainWorker, useUndrainWorker } from '../hooks/useApi'
import WorkerCard from '../components/WorkerCard'
import { InlineError } from '../components/ErrorFallback'
import { SkeletonWorkerCard } from '../components/Skeleton'
import { Server, RefreshCw, Search } from 'lucide-react'

export default function Workers() {
  const { workers: realtimeWorkers } = useStore()
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')

  const { data: apiWorkers, isLoading, error, refetch } = useWorkers()
  const drainMutation = useDrainWorker()
  const undrainMutation = useUndrainWorker()

  const workers = realtimeWorkers.length > 0 ? realtimeWorkers : (apiWorkers || [])

  // Filter workers
  const filteredWorkers = workers.filter((worker) => {
    const matchesSearch =
      worker.hostname.toLowerCase().includes(searchQuery.toLowerCase()) ||
      worker.worker_id.toLowerCase().includes(searchQuery.toLowerCase())

    const matchesStatus = statusFilter === 'all' || worker.status === statusFilter

    return matchesSearch && matchesStatus
  })

  // Stats
  const totalWorkers = workers.length
  const readyWorkers = workers.filter((w) => w.status === 'ready').length
  const busyWorkers = workers.filter((w) => w.status === 'busy').length
  const offlineWorkers = workers.filter((w) => w.status === 'offline').length

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Workers</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Manage and monitor cluster workers
          </p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isLoading}
          className="btn-secondary flex items-center gap-2 disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="card text-center">
          <p className="text-2xl font-bold text-gray-900 dark:text-white">{totalWorkers}</p>
          <p className="text-sm text-gray-500">Total</p>
        </div>
        <div className="card text-center">
          <p className="text-2xl font-bold text-green-600">{readyWorkers}</p>
          <p className="text-sm text-gray-500">Ready</p>
        </div>
        <div className="card text-center">
          <p className="text-2xl font-bold text-yellow-600">{busyWorkers}</p>
          <p className="text-sm text-gray-500">Busy</p>
        </div>
        <div className="card text-center">
          <p className="text-2xl font-bold text-red-600">{offlineWorkers}</p>
          <p className="text-sm text-gray-500">Offline</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search workers..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="input pl-10"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="input w-auto"
        >
          <option value="all">All Status</option>
          <option value="ready">Ready</option>
          <option value="busy">Busy</option>
          <option value="draining">Draining</option>
          <option value="offline">Offline</option>
        </select>
      </div>

      {/* Error State */}
      {error && (
        <div className="mb-6">
          <InlineError
            message="Failed to load workers"
            onRetry={() => refetch()}
          />
        </div>
      )}

      {/* Workers Grid */}
      {isLoading && workers.length === 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonWorkerCard key={i} />
          ))}
        </div>
      ) : filteredWorkers.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredWorkers.map((worker) => (
            <WorkerCard
              key={worker.worker_id}
              worker={worker}
              onDrain={() => drainMutation.mutate(worker.worker_id)}
              onUndrain={() => undrainMutation.mutate(worker.worker_id)}
            />
          ))}
        </div>
      ) : (
        <div className="card text-center py-12">
          <Server className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
            No workers found
          </h3>
          <p className="text-gray-500">
            {searchQuery || statusFilter !== 'all'
              ? 'Try adjusting your filters'
              : 'Start a worker to begin processing jobs'}
          </p>
        </div>
      )}
    </div>
  )
}
