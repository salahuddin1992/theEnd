import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useEffect } from 'react'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Workers from './pages/Workers'
import Jobs from './pages/Jobs'
import AITasks from './pages/AITasks'
import Metrics from './pages/Metrics'
import Settings from './pages/Settings'
import { useStore } from './store'

function App() {
  const { darkMode, initWebSocket } = useStore()

  useEffect(() => {
    // Apply dark mode
    if (darkMode) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [darkMode])

  useEffect(() => {
    // Initialize WebSocket connection
    initWebSocket()
  }, [initWebSocket])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="workers" element={<Workers />} />
          <Route path="jobs" element={<Jobs />} />
          <Route path="ai-tasks" element={<AITasks />} />
          <Route path="metrics" element={<Metrics />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
