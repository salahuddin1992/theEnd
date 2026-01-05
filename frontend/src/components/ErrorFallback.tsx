import { AlertTriangle, RefreshCw, Home } from 'lucide-react'
import type { FallbackProps } from 'react-error-boundary'

export function ErrorFallback({ error, resetErrorBoundary }: FallbackProps) {
  return (
    <div className="min-h-[400px] flex items-center justify-center p-8">
      <div className="text-center max-w-md">
        <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
          <AlertTriangle className="w-8 h-8 text-red-600 dark:text-red-400" />
        </div>
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
          Something went wrong
        </h2>
        <p className="text-gray-600 dark:text-gray-400 mb-2">
          {error.message || 'An unexpected error occurred'}
        </p>
        {import.meta.env.DEV && error.stack && (
          <pre className="text-left text-xs bg-gray-100 dark:bg-gray-800 p-3 rounded-lg mb-4 overflow-auto max-h-32">
            {error.stack}
          </pre>
        )}
        <div className="flex gap-3 justify-center">
          <button
            onClick={resetErrorBoundary}
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Try Again
          </button>
          <button
            onClick={() => window.location.href = '/'}
            className="inline-flex items-center gap-2 px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
          >
            <Home className="w-4 h-4" />
            Go Home
          </button>
        </div>
      </div>
    </div>
  )
}

// Simple inline error display for smaller components
interface InlineErrorProps {
  message: string
  onRetry?: () => void
}

export function InlineError({ message, onRetry }: InlineErrorProps) {
  return (
    <div className="flex items-center gap-3 p-4 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
      <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0" />
      <p className="text-sm text-red-700 dark:text-red-300 flex-1">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-sm text-red-600 dark:text-red-400 hover:underline flex items-center gap-1"
        >
          <RefreshCw className="w-3 h-3" />
          Retry
        </button>
      )}
    </div>
  )
}

export default ErrorFallback
