import { useQuery } from '@tanstack/react-query'
import { useStore } from '../store'
import { fetchStats, fetchMetricsHistory } from '../api'
import StatCard from '../components/StatCard'
import ResourceChart from '../components/ResourceChart'
import {
  Server,
  Briefcase,
  Cpu,
  HardDrive,
  Activity,
  CheckCircle,
  XCircle,
  Clock,
} from 'lucide-react'

export default function Dashboard() {
  const { stats: realtimeStats, workers, jobs } = useStore()

  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: fetchStats,
    refetchInterval: 5000,
  })

  const { data: metricsHistory } = useQuery({
    queryKey: ['metrics-history'],
    queryFn: () => fetchMetricsHistory('1h'),
    refetchInterval: 30000,
  })

  const currentStats = realtimeStats || stats

  // Calculate job stats
  const runningJobs = jobs.filter((j) => j.status === 'running').length
  const pendingJobs = jobs.filter((j) => j.status === 'pending').length
  const completedJobs = jobs.filter((j) => j.status === 'completed').length
  const failedJobs = jobs.filter((j) => j.status === 'failed').length

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">
          Cluster overview and real-time monitoring
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatCard
          title="Active Workers"
          value={currentStats?.active_workers || workers.filter((w) => w.status !== 'offline').length}
          subtitle={`${currentStats?.total_workers || workers.length} total`}
          icon={Server}
          color="blue"
        />
        <StatCard
          title="Running Jobs"
          value={currentStats?.running_jobs || runningJobs}
          subtitle={`${currentStats?.pending_jobs || pendingJobs} pending`}
          icon={Activity}
          color="yellow"
        />
        <StatCard
          title="Completed Jobs"
          value={currentStats?.completed_jobs || completedJobs}
          icon={CheckCircle}
          color="green"
        />
        <StatCard
          title="Failed Jobs"
          value={currentStats?.failed_jobs || failedJobs}
          icon={XCircle}
          color="red"
        />
      </div>

      {/* Resource Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <StatCard
          title="CPU Usage"
          value={`${((currentStats?.used_cpu_cores || 0) / (currentStats?.total_cpu_cores || 1) * 100).toFixed(1)}%`}
          subtitle={`${currentStats?.used_cpu_cores || 0} / ${currentStats?.total_cpu_cores || 0} cores`}
          icon={Cpu}
          color="purple"
        />
        <StatCard
          title="Memory Usage"
          value={`${((currentStats?.used_memory_gb || 0) / (currentStats?.total_memory_gb || 1) * 100).toFixed(1)}%`}
          subtitle={`${currentStats?.used_memory_gb || 0} / ${currentStats?.total_memory_gb || 0} GB`}
          icon={HardDrive}
          color="green"
        />
        <StatCard
          title="GPU Usage"
          value={`${currentStats?.used_gpu || 0} / ${currentStats?.total_gpu || 0}`}
          subtitle="GPUs in use"
          icon={Activity}
          color="yellow"
        />
      </div>

      {/* Charts */}
      {metricsHistory && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <ResourceChart
            data={metricsHistory.cpu}
            title="CPU Usage Over Time"
            color="#8B5CF6"
          />
          <ResourceChart
            data={metricsHistory.memory}
            title="Memory Usage Over Time"
            color="#10B981"
          />
        </div>
      )}

      {/* Quick Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Workers */}
        <div className="card">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Worker Status
          </h3>
          <div className="space-y-3">
            {workers.slice(0, 5).map((worker) => (
              <div
                key={worker.worker_id}
                className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg"
              >
                <div className="flex items-center gap-3">
                  <Server className="w-4 h-4 text-gray-500" />
                  <span className="font-medium text-gray-900 dark:text-white">
                    {worker.hostname}
                  </span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-sm text-gray-500">
                    CPU: {worker.current_usage.cpu_percent.toFixed(0)}%
                  </span>
                  <span
                    className={`px-2 py-1 rounded-full text-xs font-medium ${
                      worker.status === 'ready'
                        ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                        : worker.status === 'busy'
                        ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                        : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                    }`}
                  >
                    {worker.status}
                  </span>
                </div>
              </div>
            ))}
            {workers.length === 0 && (
              <p className="text-gray-500 text-center py-4">No workers connected</p>
            )}
          </div>
        </div>

        {/* Recent Jobs */}
        <div className="card">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Recent Jobs
          </h3>
          <div className="space-y-3">
            {jobs.slice(0, 5).map((job) => (
              <div
                key={job.job_id}
                className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg"
              >
                <div className="flex items-center gap-3">
                  {job.status === 'running' ? (
                    <Activity className="w-4 h-4 text-yellow-500 animate-pulse" />
                  ) : job.status === 'completed' ? (
                    <CheckCircle className="w-4 h-4 text-green-500" />
                  ) : job.status === 'failed' ? (
                    <XCircle className="w-4 h-4 text-red-500" />
                  ) : (
                    <Clock className="w-4 h-4 text-blue-500" />
                  )}
                  <span className="font-medium text-gray-900 dark:text-white truncate max-w-[200px]">
                    {job.name}
                  </span>
                </div>
                <div className="flex items-center gap-4">
                  {job.status === 'running' && (
                    <span className="text-sm text-gray-500">{job.progress}%</span>
                  )}
                  <span
                    className={`px-2 py-1 rounded-full text-xs font-medium ${
                      job.status === 'completed'
                        ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                        : job.status === 'running'
                        ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                        : job.status === 'failed'
                        ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                        : 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                    }`}
                  >
                    {job.status}
                  </span>
                </div>
              </div>
            ))}
            {jobs.length === 0 && (
              <p className="text-gray-500 text-center py-4">No jobs submitted</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
