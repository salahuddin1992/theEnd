import { useState } from 'react'
import { useStore } from '../store'
import {
  Sun,
  Server,
  Bell,
  Globe,
  Save,
} from 'lucide-react'
import clsx from 'clsx'

export default function Settings() {
  const { darkMode, toggleDarkMode, wsConnected } = useStore()
  const [masterUrl, setMasterUrl] = useState('http://localhost:8765')
  const [notifications, setNotifications] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [refreshInterval, setRefreshInterval] = useState(5)

  const handleSave = () => {
    // Save settings to localStorage
    localStorage.setItem('nebula-settings', JSON.stringify({
      masterUrl,
      notifications,
      autoRefresh,
      refreshInterval,
    }))
    alert('Settings saved!')
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Settings</h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">
          Configure your dashboard preferences
        </p>
      </div>

      <div className="space-y-6">
        {/* Appearance */}
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <Sun className="w-5 h-5" />
            Appearance
          </h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-gray-900 dark:text-white">Dark Mode</p>
                <p className="text-sm text-gray-500">Toggle dark/light theme</p>
              </div>
              <button
                onClick={toggleDarkMode}
                className={clsx(
                  'relative w-14 h-7 rounded-full transition-colors',
                  darkMode ? 'bg-nebula-600' : 'bg-gray-300'
                )}
              >
                <span
                  className={clsx(
                    'absolute top-1 w-5 h-5 bg-white rounded-full transition-transform shadow-sm',
                    darkMode ? 'left-8' : 'left-1'
                  )}
                />
              </button>
            </div>
          </div>
        </div>

        {/* Connection */}
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <Server className="w-5 h-5" />
            Connection
          </h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Master Server URL
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="text"
                  value={masterUrl}
                  onChange={(e) => setMasterUrl(e.target.value)}
                  className="input flex-1"
                  placeholder="http://localhost:8765"
                />
                <span
                  className={clsx(
                    'px-3 py-2 rounded-lg text-sm font-medium',
                    wsConnected
                      ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                      : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                  )}
                >
                  {wsConnected ? 'Connected' : 'Disconnected'}
                </span>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-gray-900 dark:text-white">Auto Refresh</p>
                <p className="text-sm text-gray-500">Automatically refresh data</p>
              </div>
              <button
                onClick={() => setAutoRefresh(!autoRefresh)}
                className={clsx(
                  'relative w-14 h-7 rounded-full transition-colors',
                  autoRefresh ? 'bg-nebula-600' : 'bg-gray-300'
                )}
              >
                <span
                  className={clsx(
                    'absolute top-1 w-5 h-5 bg-white rounded-full transition-transform shadow-sm',
                    autoRefresh ? 'left-8' : 'left-1'
                  )}
                />
              </button>
            </div>

            {autoRefresh && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Refresh Interval (seconds)
                </label>
                <input
                  type="number"
                  min="1"
                  max="60"
                  value={refreshInterval}
                  onChange={(e) => setRefreshInterval(Number(e.target.value))}
                  className="input w-32"
                />
              </div>
            )}
          </div>
        </div>

        {/* Notifications */}
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <Bell className="w-5 h-5" />
            Notifications
          </h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-gray-900 dark:text-white">Enable Notifications</p>
                <p className="text-sm text-gray-500">Get alerts for job status changes</p>
              </div>
              <button
                onClick={() => setNotifications(!notifications)}
                className={clsx(
                  'relative w-14 h-7 rounded-full transition-colors',
                  notifications ? 'bg-nebula-600' : 'bg-gray-300'
                )}
              >
                <span
                  className={clsx(
                    'absolute top-1 w-5 h-5 bg-white rounded-full transition-transform shadow-sm',
                    notifications ? 'left-8' : 'left-1'
                  )}
                />
              </button>
            </div>
          </div>
        </div>

        {/* About */}
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <Globe className="w-5 h-5" />
            About
          </h2>
          <div className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
            <p>
              <span className="font-medium text-gray-900 dark:text-white">NebulaCompute Dashboard</span>
            </p>
            <p>Version: 1.0.0</p>
            <p>A modern distributed computing platform</p>
          </div>
        </div>

        {/* Save Button */}
        <div className="flex justify-end">
          <button onClick={handleSave} className="btn-primary flex items-center gap-2">
            <Save className="w-4 h-4" />
            Save Settings
          </button>
        </div>
      </div>
    </div>
  )
}
