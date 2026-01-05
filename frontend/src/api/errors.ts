import { AxiosError } from 'axios'

export interface ApiErrorResponse {
  message: string
  code?: string
  details?: Record<string, unknown>
}

export class ApiError extends Error {
  code: string
  status: number
  details?: Record<string, unknown>

  constructor(message: string, status: number, code?: string, details?: Record<string, unknown>) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code || 'UNKNOWN_ERROR'
    this.details = details
  }

  static fromAxiosError(error: AxiosError<ApiErrorResponse>): ApiError {
    const status = error.response?.status || 500
    const data = error.response?.data

    // Handle network errors
    if (!error.response) {
      return new ApiError(
        'Network error. Please check your connection.',
        0,
        'NETWORK_ERROR'
      )
    }

    // Handle timeout
    if (error.code === 'ECONNABORTED') {
      return new ApiError(
        'Request timed out. Please try again.',
        408,
        'TIMEOUT_ERROR'
      )
    }

    // Handle specific HTTP status codes
    const statusMessages: Record<number, string> = {
      400: 'Invalid request',
      401: 'Authentication required',
      403: 'Access denied',
      404: 'Resource not found',
      409: 'Conflict with current state',
      422: 'Validation error',
      429: 'Too many requests. Please slow down.',
      500: 'Internal server error',
      502: 'Server is temporarily unavailable',
      503: 'Service unavailable. Please try again later.',
    }

    const message = data?.message || statusMessages[status] || 'An unexpected error occurred'
    const code = data?.code || `HTTP_${status}`

    return new ApiError(message, status, code, data?.details)
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

export function getErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    return error.message
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'An unexpected error occurred'
}
