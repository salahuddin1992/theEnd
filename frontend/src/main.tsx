import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { ErrorBoundary } from 'react-error-boundary'
import { Toaster } from 'react-hot-toast'
import { queryClient } from './lib/queryClient'
import { ErrorFallback } from './components/ErrorFallback'
import App from './App'
import './index.css'

function handleGlobalError(error: Error, info: React.ErrorInfo) {
  console.error('Global error boundary caught:', error, info)
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary FallbackComponent={ErrorFallback} onError={handleGlobalError}>
      <QueryClientProvider client={queryClient}>
        <App />
        <Toaster
          position="top-right"
          toastOptions={{
            duration: 4000,
            style: {
              background: 'var(--toast-bg, #fff)',
              color: 'var(--toast-color, #1f2937)',
              borderRadius: '0.75rem',
              boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)',
            },
            success: {
              iconTheme: {
                primary: '#10b981',
                secondary: '#fff',
              },
            },
            error: {
              iconTheme: {
                primary: '#ef4444',
                secondary: '#fff',
              },
              duration: 5000,
            },
          }}
        />
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)
