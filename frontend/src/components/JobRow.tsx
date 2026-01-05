import type { Job } from '../store'
import { formatDistanceToNow } from 'date-fns'
import { Play, CheckCircle, XCircle, Clock, Ban, AlertCircle } from 'lucide-react'
import clsx from 'clsx'

interface JobRowProps {
  job: Job
  onCancel?: () => void
  onClick?: () => void
}

const statusConfig = {
  pending: {
    icon: Clock,
    color: 'text-blue-500',
    bg: 'bg-blue-100 dark:bg-blue-900/30',
    label: 'Pending',
  },
  running: {
    icon: Play,
    color: 'text-yellow-500',
    bg: 'bg-yellow-100 dark:bg-yellow-900/30',
    label: 'Running',
  },
  completed: {
    icon: CheckCircle,
    color: 'text-green-500',
    bg: 'bg-green-100 dark:bg-green-900/30',
    label: 'Completed',
  },
  failed: {
    icon: XCircle,
    color: 'text-red-500',
    bg: 'bg-red-100 dark:bg-red-900/30',
    label: 'Failed',
  },
  cancelled: {
    icon: Ban,
    color: 'text-gray-500',
    bg: 'bg-gray-100 dark:bg-gray-900/30',
    label: 'Cancelled',
  },
  timeout: {
    icon: AlertCircle,
    color: 'text-orange-500',
    bg: 'bg-orange-100 dark:bg-orange-900/30',
    label: 'Timeout',
  },
}

export default function JobRow({ job, onCancel, onClick }: JobRowProps) {
  const config = statusConfig[job.status]
  const StatusIcon = config.icon

  return (
    <div
      className={clsx(
        'p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700',
        'hover:shadow-sm transition-all',
        onClick && 'cursor-pointer'
      )}
      onClick={onClick}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className={clsx('p-2 rounded-lg', config.bg)}>
            <StatusIcon className={clsx('w-5 h-5', config.color)} />
          </div>
          <div>
            <h4 className="font-medium text-gray-900 dark:text-white">{job.name}</h4>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {job.job_id.slice(0, 12)}... • {job.queue || 'default'} queue
            </p>
          </div>
        </div>

        <div className="flex items-center gap-6">
          {/* Progress */}
          {job.status === 'running' && (
            <div className="w-32">
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="text-gray-500">Progress</span>
                <span className="text-gray-700 dark:text-gray-300 font-medium">
                  {job.progress}%
                </span>
              </div>
              <div className="h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-nebula-500 rounded-full transition-all"
                  style={{ width: `${job.progress}%` }}
                />
              </div>
            </div>
          )}

          {/* Worker */}
          {job.worker_id && (
            <div className="text-right">
              <p className="text-xs text-gray-500 dark:text-gray-400">Worker</p>
              <p className="text-sm text-gray-700 dark:text-gray-300">
                {job.worker_id.slice(0, 8)}...
              </p>
            </div>
          )}

          {/* Time */}
          <div className="text-right min-w-[100px]">
            <p className="text-xs text-gray-500 dark:text-gray-400">Created</p>
            <p className="text-sm text-gray-700 dark:text-gray-300">
              {formatDistanceToNow(new Date(job.created_at), { addSuffix: true })}
            </p>
          </div>

          {/* Priority */}
          <div className="text-right">
            <p className="text-xs text-gray-500 dark:text-gray-400">Priority</p>
            <p className="text-sm text-gray-700 dark:text-gray-300">{job.priority}</p>
          </div>

          {/* Cancel button */}
          {(job.status === 'pending' || job.status === 'running') && onCancel && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                onCancel()
              }}
              className="px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      {/* Error message */}
      {job.error && (
        <div className="mt-3 p-2 bg-red-50 dark:bg-red-900/20 rounded-lg">
          <p className="text-sm text-red-600 dark:text-red-400">{job.error}</p>
        </div>
      )}
    </div>
  )
}
