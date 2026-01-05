import { Outlet, NavLink } from 'react-router-dom'
import { useStore } from '../store'
import {
  LayoutDashboard,
  Server,
  Briefcase,
  Brain,
  BarChart3,
  Settings,
  Moon,
  Sun,
  Menu,
  Wifi,
  WifiOff,
  ChevronLeft,
} from 'lucide-react'
import clsx from 'clsx'

const navItems = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/workers', icon: Server, label: 'Workers' },
  { to: '/jobs', icon: Briefcase, label: 'Jobs' },
  { to: '/ai-tasks', icon: Brain, label: 'AI Tasks' },
  { to: '/metrics', icon: BarChart3, label: 'Metrics' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export default function Layout() {
  const { darkMode, toggleDarkMode, sidebarOpen, toggleSidebar, wsConnected } = useStore()

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-900">
      {/* Sidebar */}
      <aside
        className={clsx(
          'bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700',
          'transition-all duration-300 flex flex-col',
          sidebarOpen ? 'w-64' : 'w-20'
        )}
      >
        {/* Logo */}
        <div className="h-16 flex items-center justify-between px-4 border-b border-gray-200 dark:border-gray-700">
          {sidebarOpen && (
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-gradient-to-br from-nebula-500 to-nebula-700 rounded-lg flex items-center justify-center">
                <span className="text-white font-bold text-sm">N</span>
              </div>
              <span className="font-semibold text-lg text-gray-900 dark:text-white">
                NebulaCompute
              </span>
            </div>
          )}
          <button
            onClick={toggleSidebar}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          >
            {sidebarOpen ? (
              <ChevronLeft className="w-5 h-5 text-gray-500" />
            ) : (
              <Menu className="w-5 h-5 text-gray-500" />
            )}
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-4 px-3 space-y-1">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors',
                  isActive
                    ? 'bg-nebula-50 dark:bg-nebula-900/30 text-nebula-600 dark:text-nebula-400'
                    : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
                )
              }
            >
              <Icon className="w-5 h-5 flex-shrink-0" />
              {sidebarOpen && <span className="font-medium">{label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* Bottom section */}
        <div className="p-4 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            {/* Connection status */}
            <div className={clsx('flex items-center gap-2', sidebarOpen ? '' : 'justify-center w-full')}>
              {wsConnected ? (
                <Wifi className="w-4 h-4 text-green-500" />
              ) : (
                <WifiOff className="w-4 h-4 text-red-500" />
              )}
              {sidebarOpen && (
                <span className={clsx('text-sm', wsConnected ? 'text-green-600' : 'text-red-600')}>
                  {wsConnected ? 'Connected' : 'Disconnected'}
                </span>
              )}
            </div>

            {/* Theme toggle */}
            {sidebarOpen && (
              <button
                onClick={toggleDarkMode}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              >
                {darkMode ? (
                  <Sun className="w-5 h-5 text-yellow-500" />
                ) : (
                  <Moon className="w-5 h-5 text-gray-500" />
                )}
              </button>
            )}
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
