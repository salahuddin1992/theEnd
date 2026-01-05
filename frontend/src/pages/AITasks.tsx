import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import {
  fetchAITasks,
  fetchAIProviders,
  fetchAIModels,
  submitAITask,
  cancelAITask,
  type AITaskRequest,
} from '../api'
import {
  Brain,
  Plus,
  RefreshCw,
  X,
  Zap,
  GraduationCap,
  Database,
  Sparkles,
  CheckCircle,
  Clock,
  XCircle,
} from 'lucide-react'
import clsx from 'clsx'

const taskTypeConfig = {
  inference: { icon: Zap, label: 'Inference', color: 'text-blue-500' },
  training: { icon: GraduationCap, label: 'Training', color: 'text-purple-500' },
  embedding: { icon: Database, label: 'Embedding', color: 'text-green-500' },
  'fine-tune': { icon: Sparkles, label: 'Fine-tune', color: 'text-orange-500' },
}

export default function AITasks() {
  const [showTaskModal, setShowTaskModal] = useState(false)
  const [selectedType, setSelectedType] = useState<'inference' | 'training' | 'embedding' | 'fine-tune' | null>(null)
  const queryClient = useQueryClient()

  const { data: tasks, isLoading, refetch } = useQuery({
    queryKey: ['ai-tasks'],
    queryFn: fetchAITasks,
    refetchInterval: 5000,
  })

  const { data: providers } = useQuery({
    queryKey: ['ai-providers'],
    queryFn: fetchAIProviders,
  })

  const { data: models } = useQuery({
    queryKey: ['ai-models'],
    queryFn: fetchAIModels,
  })

  const cancelMutation = useMutation({
    mutationFn: cancelAITask,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['ai-tasks'] }),
  })

  const submitMutation = useMutation({
    mutationFn: submitAITask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ai-tasks'] })
      setShowTaskModal(false)
      setSelectedType(null)
    },
  })

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">AI Tasks</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Distributed AI inference, training, and more
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
            onClick={() => setShowTaskModal(true)}
            className="btn-primary flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            New AI Task
          </button>
        </div>
      </div>

      {/* Task Type Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {Object.entries(taskTypeConfig).map(([type, config]) => {
          const Icon = config.icon
          const count = tasks?.filter((t) => t.type === type).length || 0
          const running = tasks?.filter((t) => t.type === type && t.status === 'running').length || 0

          return (
            <button
              key={type}
              onClick={() => {
                setSelectedType(type as keyof typeof taskTypeConfig)
                setShowTaskModal(true)
              }}
              className="card hover:shadow-md transition-all text-left group"
            >
              <div className="flex items-center justify-between mb-4">
                <div className={clsx('p-3 rounded-lg bg-gray-100 dark:bg-gray-700', config.color)}>
                  <Icon className="w-6 h-6" />
                </div>
                <span className="text-sm text-gray-500 group-hover:text-nebula-600">
                  Create new →
                </span>
              </div>
              <h3 className="font-semibold text-gray-900 dark:text-white">{config.label}</h3>
              <p className="text-sm text-gray-500 mt-1">
                {count} total • {running} running
              </p>
            </button>
          )
        })}
      </div>

      {/* Active Providers */}
      <div className="card mb-8">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          AI Providers
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          {providers?.map((provider) => (
            <div
              key={provider.name}
              className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg text-center"
            >
              <div className="flex items-center justify-center gap-2 mb-2">
                <span
                  className={clsx(
                    'w-2 h-2 rounded-full',
                    provider.status === 'active' ? 'bg-green-500' : 'bg-red-500'
                  )}
                />
                <span className="font-medium text-gray-900 dark:text-white">
                  {provider.name}
                </span>
              </div>
              <p className="text-xs text-gray-500">{provider.models} models</p>
            </div>
          ))}
          {!providers?.length && (
            <p className="col-span-full text-center text-gray-500 py-4">
              No providers configured
            </p>
          )}
        </div>
      </div>

      {/* Tasks List */}
      <div className="card">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Recent Tasks
        </h3>
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <RefreshCw className="w-8 h-8 text-nebula-500 animate-spin" />
          </div>
        ) : tasks && tasks.length > 0 ? (
          <div className="space-y-3">
            {tasks.map((task) => {
              const config = taskTypeConfig[task.type]
              const Icon = config.icon

              return (
                <div
                  key={task.task_id}
                  className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg flex items-center justify-between"
                >
                  <div className="flex items-center gap-4">
                    <div className={clsx('p-2 rounded-lg bg-white dark:bg-gray-800', config.color)}>
                      <Icon className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-gray-900 dark:text-white">
                          {config.label}
                        </span>
                        <span className="text-xs text-gray-500">
                          {task.task_id.slice(0, 8)}...
                        </span>
                      </div>
                      <p className="text-sm text-gray-500">{task.model}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-6">
                    {task.status === 'running' && (
                      <div className="w-32">
                        <div className="h-1.5 bg-gray-200 dark:bg-gray-600 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-nebula-500 rounded-full"
                            style={{ width: `${task.progress}%` }}
                          />
                        </div>
                        <p className="text-xs text-gray-500 mt-1 text-right">{task.progress}%</p>
                      </div>
                    )}

                    <div className="flex items-center gap-2">
                      {task.status === 'running' && (
                        <RefreshCw className="w-4 h-4 text-yellow-500 animate-spin" />
                      )}
                      {task.status === 'completed' && (
                        <CheckCircle className="w-4 h-4 text-green-500" />
                      )}
                      {task.status === 'failed' && (
                        <XCircle className="w-4 h-4 text-red-500" />
                      )}
                      {task.status === 'pending' && (
                        <Clock className="w-4 h-4 text-blue-500" />
                      )}
                      <span className="text-sm text-gray-600 dark:text-gray-300 capitalize">
                        {task.status}
                      </span>
                    </div>

                    {(task.status === 'pending' || task.status === 'running') && (
                      <button
                        onClick={() => cancelMutation.mutate(task.task_id)}
                        className="text-red-500 hover:text-red-600 text-sm"
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="text-center py-12">
            <Brain className="w-12 h-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
              No AI tasks yet
            </h3>
            <p className="text-gray-500 mb-4">
              Start a new AI task to begin processing
            </p>
          </div>
        )}
      </div>

      {/* Submit Task Modal */}
      {showTaskModal && (
        <AITaskModal
          onClose={() => {
            setShowTaskModal(false)
            setSelectedType(null)
          }}
          onSubmit={(data) => submitMutation.mutate(data)}
          isLoading={submitMutation.isPending}
          initialType={selectedType}
          models={models || []}
        />
      )}
    </div>
  )
}

function AITaskModal({
  onClose,
  onSubmit,
  isLoading,
  initialType,
  models,
}: {
  onClose: () => void
  onSubmit: (data: AITaskRequest) => void
  isLoading: boolean
  initialType: 'inference' | 'training' | 'embedding' | 'fine-tune' | null
  models: Array<{ name: string; provider: string }>
}) {
  const [formData, setFormData] = useState<AITaskRequest>({
    type: initialType || 'inference',
    model: models[0]?.name || '',
    input: '',
    distributed: false,
    num_workers: 1,
  })

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-lg mx-4">
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            New AI Task
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            onSubmit(formData)
          }}
          className="p-6 space-y-4"
        >
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Task Type
            </label>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(taskTypeConfig).map(([type, config]) => {
                const Icon = config.icon
                return (
                  <button
                    key={type}
                    type="button"
                    onClick={() => setFormData({ ...formData, type: type as AITaskRequest['type'] })}
                    className={clsx(
                      'p-3 rounded-lg border-2 flex items-center gap-2 transition-colors',
                      formData.type === type
                        ? 'border-nebula-500 bg-nebula-50 dark:bg-nebula-900/20'
                        : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
                    )}
                  >
                    <Icon className={clsx('w-5 h-5', config.color)} />
                    <span className="font-medium text-gray-900 dark:text-white">
                      {config.label}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Model
            </label>
            <select
              value={formData.model}
              onChange={(e) => setFormData({ ...formData, model: e.target.value })}
              className="input"
            >
              {models.map((model) => (
                <option key={model.name} value={model.name}>
                  {model.name} ({model.provider})
                </option>
              ))}
            </select>
          </div>

          {(formData.type === 'inference' || formData.type === 'embedding') && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Input
              </label>
              <textarea
                value={formData.input as string}
                onChange={(e) => setFormData({ ...formData, input: e.target.value })}
                className="input min-h-[100px]"
                placeholder="Enter your prompt or text..."
              />
            </div>
          )}

          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={formData.distributed}
                onChange={(e) => setFormData({ ...formData, distributed: e.target.checked })}
                className="rounded border-gray-300"
              />
              <span className="text-sm text-gray-700 dark:text-gray-300">
                Distributed execution
              </span>
            </label>

            {formData.distributed && (
              <div className="flex items-center gap-2">
                <label className="text-sm text-gray-700 dark:text-gray-300">Workers:</label>
                <input
                  type="number"
                  min="1"
                  max="16"
                  value={formData.num_workers}
                  onChange={(e) => setFormData({ ...formData, num_workers: Number(e.target.value) })}
                  className="input w-20"
                />
              </div>
            )}
          </div>

          <div className="flex justify-end gap-3 pt-4">
            <button type="button" onClick={onClose} className="btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={isLoading}>
              {isLoading ? 'Submitting...' : 'Start Task'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
