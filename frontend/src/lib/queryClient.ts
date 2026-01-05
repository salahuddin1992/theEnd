import { QueryClient, QueryCache, MutationCache } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { isApiError, getErrorMessage } from '../api/errors'

export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error, query) => {
      // Only show toast for errors that haven't been handled by the component
      if (query.meta?.showErrorToast !== false) {
        const message = getErrorMessage(error)
        // Don't show toast for 404s on optional resources
        if (isApiError(error) && error.status === 404 && query.meta?.optional) {
          return
        }
        toast.error(message, {
          id: `query-error-${query.queryHash}`,
        })
      }
    },
  }),
  mutationCache: new MutationCache({
    onError: (error, _variables, _context, mutation) => {
      // Show error toast for mutations unless disabled
      if (mutation.meta?.showErrorToast !== false) {
        const message = getErrorMessage(error)
        toast.error(message)
      }
    },
    onSuccess: (_data, _variables, _context, mutation) => {
      // Show success toast if configured
      if (mutation.meta?.successMessage) {
        toast.success(mutation.meta.successMessage as string)
      }
    },
  }),
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        // Don't retry on client errors (4xx)
        if (isApiError(error) && error.status >= 400 && error.status < 500) {
          return false
        }
        return failureCount < 2
      },
      staleTime: 5000,
      gcTime: 10 * 60 * 1000, // 10 minutes
    },
    mutations: {
      retry: false,
    },
  },
})

// Types for meta options
export interface CustomQueryMeta {
  showErrorToast?: boolean
  optional?: boolean
}

export interface CustomMutationMeta {
  showErrorToast?: boolean
  successMessage?: string
}
