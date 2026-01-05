import type { Worker } from '../store'
import { Server, Cpu, HardDrive, Activity } from 'lucide-react'
import clsx from 'clsx'

interface WorkerCardProps {
  worker: Worker
  onDrain?: () => void
  onUndrain?: () => void
}

const statusColors = {
  ready: 'bg-green-500',
  busy: 'bg-yellow-500',
  offline: 'bg-red-500',
  draining: 'bg-orange-500',
}

const statusLabels = {
  ready: 'Ready',
  busy: 'Busy',
  offline: 'Offline',
  draining: 'Draining',
}

export default function WorkerCard({ worker, onDrain, onUndrain }: WorkerCardProps) {
  return (
    <div className="card hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-nebula-100 dark:bg-nebula-900/30 rounded-lg">
            <Server className="w-5 h-5 text-nebula-600 dark:text-nebula-400" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white">
              {worker.hostname}
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {worker.worker_id.slice(0, 8)}...
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={clsx('w-2 h-2 rounded-full', statusColors[worker.status])} />
          <span className="text-sm text-gray-600 dark:text-gray-300">
            {statusLabels[worker.status]}
          </span>
        </div>
      </div>

      {/* Resources */}
      <div className="space-y-3">
        {/* CPU */}
        <div>
          <div className="flex items-center justify-between text-sm mb-1">
            <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-400">
              <Cpu className="w-4 h-4" />
              <span>CPU</span>
            </div>
            <span className="text-gray-900 dark:text-white font-medium">
              {worker.current_usage.cpu_percent.toFixed(1)}%
            </span>
          </div>
          <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-nebula-500 rounded-full transition-all"
              style={{ width: `${Math.min(worker.current_usage.cpu_percent, 100)}%` }}
            />
          </div>
          <p className="text-xs text-gray-500 mt-1">{worker.resources.cpu_cores} cores</p>
        </div>

        {/* Memory */}
        <div>
          <div className="flex items-center justify-between text-sm mb-1">
            <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-400">
              <HardDrive className="w-4 h-4" />
              <span>Memory</span>
            </div>
            <span className="text-gray-900 dark:text-white font-medium">
              {worker.current_usage.memory_percent.toFixed(1)}%
            </span>
          </div>
          <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-green-500 rounded-full transition-all"
              style={{ width: `${Math.min(worker.current_usage.memory_percent, 100)}%` }}
            />
          </div>
          <p className="text-xs text-gray-500 mt-1">
            {(worker.resources.memory_mb / 1024).toFixed(1)} GB
          </p>
        </div>

        {/* GPU */}
        {worker.resources.gpu_count > 0 && (
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-1.5 text-gray-600 dark:text-gray-400">
              <Activity className="w-4 h-4" />
              <span>GPU</span>
            </div>
            <span className="text-gray-900 dark:text-white font-medium">
              {worker.resources.gpu_count} units
            </span>
          </div>
        )}
      </div>

      {/* Jobs */}
      <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-600 dark:text-gray-400">Running Jobs</span>
          <span className="text-sm font-medium text-gray-900 dark:text-white">
            {worker.jobs_running}
          </span>
        </div>
      </div>

      {/* Actions */}
      {(onDrain || onUndrain) && (
        <div className="mt-4 flex gap-2">
          {worker.status !== 'draining' && worker.status !== 'offline' && onDrain && (
            <button
              onClick={onDrain}
              className="flex-1 btn-secondary text-sm"
            >
              Drain
            </button>
          )}
          {worker.status === 'draining' && onUndrain && (
            <button
              onClick={onUndrain}
              className="flex-1 btn-primary text-sm"
            >
              Undrain
            </button>
          )}
        </div>
      )}
    </div>
  )
}
