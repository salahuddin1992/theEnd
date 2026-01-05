import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import * as api from '../api'
import type { SubmitJobRequest, AITaskRequest } from '../api'

// Query Keys
export const queryKeys = {
  stats: ['stats'] as const,
  workers: ['workers'] as const,
  jobs: (params?: { status?: string; queue?: string; limit?: number }) =>
    ['jobs', params] as const,
  job: (id: string) => ['jobs', id] as const,
  aiTasks: ['ai-tasks'] as const,
  aiProviders: ['ai-providers'] as const,
  aiModels: ['ai-models'] as const,
  metricsHistory: (duration: string) => ['metrics', 'history', duration] as const,
}

// Stats
export function useStats() {
  return useQuery({
    queryKey: queryKeys.stats,
    queryFn: api.fetchStats,
    refetchInterval: 5000,
  })
}

// Workers
export function useWorkers() {
  return useQuery({
    queryKey: queryKeys.workers,
    queryFn: api.fetchWorkers,
    refetchInterval: 5000,
  })
}

export function useDrainWorker() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: api.drainWorker,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.workers })
      toast.success('Worker drained successfully')
    },
    meta: { showErrorToast: true },
  })
}

export function useUndrainWorker() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: api.undrainWorker,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.workers })
      toast.success('Worker activated successfully')
    },
    meta: { showErrorToast: true },
  })
}

// Jobs
export function useJobs(params?: { status?: string; queue?: string; limit?: number }) {
  return useQuery({
    queryKey: queryKeys.jobs(params),
    queryFn: () => api.fetchJobs(params),
    refetchInterval: 5000,
  })
}

export function useJob(jobId: string) {
  return useQuery({
    queryKey: queryKeys.job(jobId),
    queryFn: () => api.getJob(jobId),
    enabled: !!jobId,
  })
}

export function useSubmitJob() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (job: SubmitJobRequest) => api.submitJob(job),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.jobs() })
      toast.success(`Job submitted: ${data.job_id}`)
    },
    meta: { showErrorToast: true },
  })
}

export function useCancelJob() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: api.cancelJob,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.jobs() })
      toast.success('Job cancelled successfully')
    },
    meta: { showErrorToast: true },
  })
}

// AI Tasks
export function useAITasks() {
  return useQuery({
    queryKey: queryKeys.aiTasks,
    queryFn: api.fetchAITasks,
    refetchInterval: 5000,
  })
}

export function useSubmitAITask() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (task: AITaskRequest) => api.submitAITask(task),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.aiTasks })
      toast.success(`AI Task submitted: ${data.task_id}`)
    },
    meta: { showErrorToast: true },
  })
}

export function useCancelAITask() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: api.cancelAITask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.aiTasks })
      toast.success('AI Task cancelled successfully')
    },
    meta: { showErrorToast: true },
  })
}

// AI Providers & Models
export function useAIProviders() {
  return useQuery({
    queryKey: queryKeys.aiProviders,
    queryFn: api.fetchAIProviders,
    staleTime: 30000, // 30 seconds
  })
}

export function useAIModels() {
  return useQuery({
    queryKey: queryKeys.aiModels,
    queryFn: api.fetchAIModels,
    staleTime: 30000,
  })
}

// Metrics
export function useMetricsHistory(duration: '1h' | '6h' | '24h' | '7d' = '1h') {
  return useQuery({
    queryKey: queryKeys.metricsHistory(duration),
    queryFn: () => api.fetchMetricsHistory(duration),
    refetchInterval: 10000,
  })
}

// File Upload
export function useUploadFile() {
  return useMutation({
    mutationFn: ({ file, targetWorker }: { file: File; targetWorker?: string }) =>
      api.uploadFile(file, targetWorker),
    onSuccess: () => {
      toast.success('File uploaded successfully')
    },
    meta: { showErrorToast: true },
  })
}
