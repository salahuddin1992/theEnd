import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useStore } from '../store'
import { fetchJobs, submitJob, cancelJob, type SubmitJobRequest } from '../api'
import JobRow from '../components/JobRow'
import { Plus, Search, RefreshCw, X, Briefcase } from 'lucide-react'
import clsx from 'clsx'

export default function Jobs() {
  const { jobs: realtimeJobs } = useStore()
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [showSubmitModal, setShowSubmitModal] = useState(false)
  const queryClient = useQueryClient()

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['jobs', statusFilter],
    queryFn: () => fetchJobs({
      status: statusFilter === 'all' ? undefined : statusFilter,
      limit: 100,
    }),
    refetchInterval: 5000,
  })

  const jobs = realtimeJobs.length > 0 ? realtimeJobs : (data?.jobs || [])

  const cancelMutation = useMutation({
    mutationFn: cancelJob,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  const submitMutation = useMutation({
    mutationFn: submitJob,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      setShowSubmitModal(false)
    },
  })

  // Filter jobs
  const filteredJobs = jobs.filter((job) =>
    job.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    job.job_id.toLowerCase().includes(searchQuery.toLowerCase())
  )

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Jobs</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Submit and manage computing jobs
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => refetch()}
            className="btn-secondary flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
          <button
            onClick={() => setShowSubmitModal(true)}
            className="btn-primary flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            Submit Job
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search jobs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="input pl-10"
          />
        </div>
        <div className="flex items-center gap-2">
          {['all', 'pending', 'running', 'completed', 'failed'].map((status) => (
            <button
              key={status}
              onClick={() => setStatusFilter(status)}
              className={clsx(
                'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
                statusFilter === status
                  ? 'bg-nebula-100 text-nebula-700 dark:bg-nebula-900/30 dark:text-nebula-400'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
              )}
            >
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Jobs List */}
      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <RefreshCw className="w-8 h-8 text-nebula-500 animate-spin" />
        </div>
      ) : filteredJobs.length > 0 ? (
        <div className="space-y-3">
          {filteredJobs.map((job) => (
            <JobRow
              key={job.job_id}
              job={job}
              onCancel={() => cancelMutation.mutate(job.job_id)}
            />
          ))}
        </div>
      ) : (
        <div className="card text-center py-12">
          <Briefcase className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
            No jobs found
          </h3>
          <p className="text-gray-500 mb-4">
            {searchQuery || statusFilter !== 'all'
              ? 'Try adjusting your filters'
              : 'Submit a job to start processing'}
          </p>
          <button
            onClick={() => setShowSubmitModal(true)}
            className="btn-primary"
          >
            Submit Your First Job
          </button>
        </div>
      )}

      {/* Submit Modal */}
      {showSubmitModal && (
        <SubmitJobModal
          onClose={() => setShowSubmitModal(false)}
          onSubmit={(data) => submitMutation.mutate(data)}
          isLoading={submitMutation.isPending}
        />
      )}
    </div>
  )
}

function SubmitJobModal({
  onClose,
  onSubmit,
  isLoading,
}: {
  onClose: () => void
  onSubmit: (data: SubmitJobRequest) => void
  isLoading: boolean
}) {
  const [formData, setFormData] = useState<SubmitJobRequest>({
    command: '',
    name: '',
    resources: {
      cpu_cores: 1,
      memory_mb: 512,
      gpu_count: 0,
    },
    priority: 50,
    timeout_seconds: 3600,
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSubmit(formData)
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-lg mx-4">
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Submit New Job
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Job Name
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="input"
              placeholder="My Job"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Command *
            </label>
            <textarea
              value={formData.command}
              onChange={(e) => setFormData({ ...formData, command: e.target.value })}
              className="input min-h-[100px] font-mono text-sm"
              placeholder="python train.py --epochs 100"
              required
            />
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                CPU Cores
              </label>
              <input
                type="number"
                min="1"
                max="64"
                value={formData.resources?.cpu_cores}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    resources: { ...formData.resources!, cpu_cores: Number(e.target.value) },
                  })
                }
                className="input"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Memory (MB)
              </label>
              <input
                type="number"
                min="128"
                step="128"
                value={formData.resources?.memory_mb}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    resources: { ...formData.resources!, memory_mb: Number(e.target.value) },
                  })
                }
                className="input"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                GPUs
              </label>
              <input
                type="number"
                min="0"
                max="8"
                value={formData.resources?.gpu_count}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    resources: { ...formData.resources!, gpu_count: Number(e.target.value) },
                  })
                }
                className="input"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Priority (0-200)
              </label>
              <input
                type="number"
                min="0"
                max="200"
                value={formData.priority}
                onChange={(e) => setFormData({ ...formData, priority: Number(e.target.value) })}
                className="input"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Timeout (seconds)
              </label>
              <input
                type="number"
                min="60"
                value={formData.timeout_seconds}
                onChange={(e) =>
                  setFormData({ ...formData, timeout_seconds: Number(e.target.value) })
                }
                className="input"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Docker Image (optional)
            </label>
            <input
              type="text"
              value={formData.docker_image || ''}
              onChange={(e) => setFormData({ ...formData, docker_image: e.target.value })}
              className="input"
              placeholder="python:3.11-slim"
            />
          </div>

          <div className="flex justify-end gap-3 pt-4">
            <button type="button" onClick={onClose} className="btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={isLoading}>
              {isLoading ? 'Submitting...' : 'Submit Job'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
