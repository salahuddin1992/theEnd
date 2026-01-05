import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface Worker {
  worker_id: string
  hostname: string
  status: 'ready' | 'busy' | 'offline' | 'draining'
  resources: {
    cpu_cores: number
    memory_mb: number
    gpu_count: number
  }
  current_usage: {
    cpu_percent: number
    memory_percent: number
  }
  jobs_running: number
  last_heartbeat: string
  pool?: string
  tags?: string[]
}

export interface Job {
  job_id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'timeout'
  worker_id?: string
  progress: number
  created_at: string
  started_at?: string
  completed_at?: string
  error?: string
  priority: number
  queue?: string
}

export interface ClusterStats {
  total_workers: number
  active_workers: number
  total_jobs: number
  running_jobs: number
  completed_jobs: number
  failed_jobs: number
  pending_jobs: number
  total_cpu_cores: number
  used_cpu_cores: number
  total_memory_gb: number
  used_memory_gb: number
  total_gpu: number
  used_gpu: number
}

interface AppState {
  // Data
  workers: Worker[]
  jobs: Job[]
  stats: ClusterStats | null

  // UI
  darkMode: boolean
  sidebarOpen: boolean

  // WebSocket
  wsConnected: boolean
  ws: WebSocket | null

  // Actions
  setWorkers: (workers: Worker[]) => void
  setJobs: (jobs: Job[]) => void
  setStats: (stats: ClusterStats) => void
  toggleDarkMode: () => void
  toggleSidebar: () => void
  initWebSocket: () => void
  disconnectWebSocket: () => void
}

export const useStore = create<AppState>()(
  persist(
    (set, get) => ({
      // Initial state
      workers: [],
      jobs: [],
      stats: null,
      darkMode: window.matchMedia('(prefers-color-scheme: dark)').matches,
      sidebarOpen: true,
      wsConnected: false,
      ws: null,

      // Actions
      setWorkers: (workers) => set({ workers }),
      setJobs: (jobs) => set({ jobs }),
      setStats: (stats) => set({ stats }),

      toggleDarkMode: () =>
        set((state) => ({ darkMode: !state.darkMode })),

      toggleSidebar: () =>
        set((state) => ({ sidebarOpen: !state.sidebarOpen })),

      initWebSocket: () => {
        const { ws } = get()
        if (ws) return

        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const wsUrl = `${wsProtocol}//${window.location.host}/ws`

        try {
          const socket = new WebSocket(wsUrl)

          socket.onopen = () => {
            console.log('WebSocket connected')
            set({ wsConnected: true, ws: socket })
          }

          socket.onclose = () => {
            console.log('WebSocket disconnected')
            set({ wsConnected: false, ws: null })
            // Reconnect after 3 seconds
            setTimeout(() => get().initWebSocket(), 3000)
          }

          socket.onerror = (error) => {
            console.error('WebSocket error:', error)
          }

          socket.onmessage = (event) => {
            try {
              const data = JSON.parse(event.data)
              if (data.type === 'update') {
                if (data.stats) set({ stats: data.stats })
                if (data.workers) set({ workers: data.workers })
                if (data.jobs) set({ jobs: data.jobs })
              }
            } catch (e) {
              console.error('Failed to parse WebSocket message:', e)
            }
          }

          set({ ws: socket })
        } catch (e) {
          console.error('Failed to create WebSocket:', e)
        }
      },

      disconnectWebSocket: () => {
        const { ws } = get()
        if (ws) {
          ws.close()
          set({ ws: null, wsConnected: false })
        }
      },
    }),
    {
      name: 'nebula-storage',
      partialize: (state) => ({ darkMode: state.darkMode, sidebarOpen: state.sidebarOpen }),
    }
  )
)
