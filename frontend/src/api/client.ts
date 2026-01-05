import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import toast from 'react-hot-toast'
import { ApiError, ApiErrorResponse } from './errors'

const createApiClient = (): AxiosInstance => {
  const client = axios.create({
    baseURL: '/api',
    timeout: 30000,
    headers: {
      'Content-Type': 'application/json',
    },
  })

  // Request interceptor
  client.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
      // Add auth token if available
      const token = localStorage.getItem('auth_token')
      if (token && config.headers) {
        config.headers.Authorization = `Bearer ${token}`
      }
      return config
    },
    (error) => {
      return Promise.reject(error)
    }
  )

  // Response interceptor
  client.interceptors.response.use(
    (response) => response,
    (error: AxiosError<ApiErrorResponse>) => {
      const apiError = ApiError.fromAxiosError(error)

      // Handle specific error cases
      if (apiError.status === 401) {
        // Clear auth and redirect to login (when auth is implemented)
        localStorage.removeItem('auth_token')
        // window.location.href = '/login'
      }

      // Show toast for server errors (5xx) and specific client errors
      if (apiError.status >= 500 || apiError.status === 0) {
        toast.error(apiError.message, {
          id: `error-${apiError.code}`,
          duration: 5000,
        })
      }

      return Promise.reject(apiError)
    }
  )

  return client
}

export const apiClient = createApiClient()
export default apiClient
