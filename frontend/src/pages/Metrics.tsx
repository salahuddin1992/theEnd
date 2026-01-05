import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { fetchMetricsHistory, fetchStats } from '../api'
import ResourceChart from '../components/ResourceChart'
import { BarChart3, RefreshCw, Clock } from 'lucide-react'
import clsx from 'clsx'

const timeRanges = [
  { value: '1h', label: '1 Hour' },
  { value: '6h', label: '6 Hours' },
  { value: '24h', label: '24 Hours' },
  { value: '7d', label: '7 Days' },
] as const

export default function Metrics() {
  const [timeRange, setTimeRange] = useState<'1h' | '6h' | '24h' | '7d'>('1h')

  const { data: metrics, isLoading, refetch } = useQuery({
    queryKey: ['metrics-history', timeRange],
    queryFn: () => fetchMetricsHistory(timeRange),
    refetchInterval: 30000,
  })

  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: fetchStats,
    refetchInterval: 5000,
  })

  // Calculate averages
  const avgCpu = metrics?.cpu?.length
    ? (metrics.cpu.reduce((sum, p) => sum + p.value, 0) / metrics.cpu.length).toFixed(1)
    : '0'
  const avgMemory = metrics?.memory?.length
    ? (metrics.memory.reduce((sum, p) => sum + p.value, 0) / metrics.memory.length).toFixed(1)
    : '0'
  const avgGpu = metrics?.gpu?.length
    ? (metrics.gpu.reduce((sum, p) => sum + p.value, 0) / metrics.gpu.length).toFixed(1)
    : '0'

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Metrics</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Resource usage and performance metrics
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
            {timeRanges.map(({ value, label }) => (
              <button
                key={value}
                onClick={() => setTimeRange(value)}
                className={clsx(
                  'px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
                  timeRange === value
                    ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <button
            onClick={() => refetch()}
            className="btn-secondary flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <div className="card">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-500">Avg CPU Usage</span>
            <BarChart3 className="w-4 h-4 text-purple-500" />
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">{avgCpu}%</p>
        </div>
        <div className="card">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-500">Avg Memory Usage</span>
            <BarChart3 className="w-4 h-4 text-green-500" />
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">{avgMemory}%</p>
        </div>
        <div className="card">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-500">Avg GPU Usage</span>
            <BarChart3 className="w-4 h-4 text-yellow-500" />
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">{avgGpu}%</p>
        </div>
        <div className="card">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-500">Jobs/Hour</span>
            <Clock className="w-4 h-4 text-blue-500" />
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">
            {metrics?.jobs_throughput?.length
              ? Math.round(metrics.jobs_throughput[metrics.jobs_throughput.length - 1].value)
              : 0}
          </p>
        </div>
      </div>

      {/* Charts */}
      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <RefreshCw className="w-8 h-8 text-nebula-500 animate-spin" />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Resource Usage */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ResourceChart
              data={metrics?.cpu || []}
              title="CPU Usage"
              color="#8B5CF6"
              height={250}
            />
            <ResourceChart
              data={metrics?.memory || []}
              title="Memory Usage"
              color="#10B981"
              height={250}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ResourceChart
              data={metrics?.gpu || []}
              title="GPU Usage"
              color="#F59E0B"
              height={250}
            />
            <ResourceChart
              data={metrics?.jobs_throughput || []}
              title="Job Throughput"
              color="#3B82F6"
              unit=" jobs/h"
              height={250}
            />
          </div>

          {/* Network */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ResourceChart
              data={metrics?.network_in || []}
              title="Network In"
              color="#06B6D4"
              unit=" MB/s"
              height={200}
            />
            <ResourceChart
              data={metrics?.network_out || []}
              title="Network Out"
              color="#EC4899"
              unit=" MB/s"
              height={200}
            />
          </div>
        </div>
      )}

      {/* Real-time Stats */}
      {stats && (
        <div className="mt-8 card">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Current Resource Allocation
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-gray-500">CPU Cores</span>
                <span className="text-sm font-medium text-gray-900 dark:text-white">
                  {stats.used_cpu_cores} / {stats.total_cpu_cores}
                </span>
              </div>
              <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-purple-500 rounded-full"
                  style={{
                    width: `${(stats.used_cpu_cores / stats.total_cpu_cores) * 100}%`,
                  }}
                />
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-gray-500">Memory (GB)</span>
                <span className="text-sm font-medium text-gray-900 dark:text-white">
                  {stats.used_memory_gb} / {stats.total_memory_gb}
                </span>
              </div>
              <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-green-500 rounded-full"
                  style={{
                    width: `${(stats.used_memory_gb / stats.total_memory_gb) * 100}%`,
                  }}
                />
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-gray-500">GPUs</span>
                <span className="text-sm font-medium text-gray-900 dark:text-white">
                  {stats.used_gpu} / {stats.total_gpu}
                </span>
              </div>
              <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-yellow-500 rounded-full"
                  style={{
                    width: `${(stats.used_gpu / (stats.total_gpu || 1)) * 100}%`,
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
