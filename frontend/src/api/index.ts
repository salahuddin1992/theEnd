import apiClient from './client'
import type { Worker, Job, ClusterStats } from '../store'

// Re-export error utilities
export * from './errors'
export { apiClient }

const api = apiClient

// Stats
export const fetchStats = async (): Promise<ClusterStats> => {
  const { data } = await api.get('/stats')
  return data
}

// Workers
export const fetchWorkers = async (): Promise<Worker[]> => {
  const { data } = await api.get('/workers')
  return data
}

export const drainWorker = async (workerId: string): Promise<void> => {
  await api.post(`/workers/${workerId}/drain`)
}

export const undrainWorker = async (workerId: string): Promise<void> => {
  await api.post(`/workers/${workerId}/undrain`)
}

// Jobs
export interface JobsResponse {
  jobs: Job[]
  total: number
}

export interface SubmitJobRequest {
  command: string
  name?: string
  resources?: {
    cpu_cores?: number
    memory_mb?: number
    gpu_count?: number
  }
  priority?: number
  queue?: string
  timeout_seconds?: number
  docker_image?: string
  environment?: Record<string, string>
}

export const fetchJobs = async (params?: {
  status?: string
  queue?: string
  limit?: number
}): Promise<JobsResponse> => {
  const { data } = await api.get('/jobs', { params })
  return data
}

export const getJob = async (jobId: string): Promise<Job> => {
  const { data } = await api.get(`/jobs/${jobId}`)
  return data
}

export const submitJob = async (job: SubmitJobRequest): Promise<{ job_id: string }> => {
  const { data } = await api.post('/jobs', job)
  return data
}

export const cancelJob = async (jobId: string): Promise<void> => {
  await api.delete(`/jobs/${jobId}`)
}

// AI Tasks
export interface AITask {
  task_id: string
  type: 'inference' | 'training' | 'embedding' | 'fine-tune'
  status: 'pending' | 'running' | 'completed' | 'failed'
  model: string
  progress: number
  created_at: string
  result?: unknown
}

export interface AITaskRequest {
  type: 'inference' | 'training' | 'embedding' | 'fine-tune'
  model: string
  input?: string | string[]
  config?: Record<string, unknown>
  distributed?: boolean
  num_workers?: number
}

export const fetchAITasks = async (): Promise<AITask[]> => {
  const { data } = await api.get('/ai/tasks')
  return data.tasks || []
}

export const submitAITask = async (task: AITaskRequest): Promise<{ task_id: string }> => {
  const { data } = await api.post('/ai/tasks', task)
  return data
}

export const cancelAITask = async (taskId: string): Promise<void> => {
  await api.delete(`/ai/tasks/${taskId}`)
}

// Providers
export interface AIProvider {
  name: string
  status: 'active' | 'inactive' | 'error'
  models: number
  endpoint?: string
}

export const fetchAIProviders = async (): Promise<AIProvider[]> => {
  const { data } = await api.get('/ai/providers')
  return data.providers || []
}

// Models
export interface AIModel {
  name: string
  provider: string
  size?: string
  capabilities: string[]
}

export const fetchAIModels = async (): Promise<AIModel[]> => {
  const { data } = await api.get('/ai/models')
  return data.models || []
}

// File Transfer
export const uploadFile = async (
  file: File,
  targetWorker?: string
): Promise<{ file_id: string; path: string }> => {
  const formData = new FormData()
  formData.append('file', file)
  if (targetWorker) formData.append('target_worker', targetWorker)

  const { data } = await api.post('/files/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export const downloadFile = async (fileId: string): Promise<Blob> => {
  const { data } = await api.get(`/files/${fileId}/download`, {
    responseType: 'blob',
  })
  return data
}

// Metrics History
export interface MetricPoint {
  timestamp: string
  value: number
}

export interface MetricsHistory {
  cpu: MetricPoint[]
  memory: MetricPoint[]
  gpu: MetricPoint[]
  jobs_throughput: MetricPoint[]
  network_in: MetricPoint[]
  network_out: MetricPoint[]
}

export const fetchMetricsHistory = async (
  duration: '1h' | '6h' | '24h' | '7d' = '1h'
): Promise<MetricsHistory> => {
  const { data } = await api.get('/metrics/history', { params: { duration } })
  return data
}

export default api
