// Shared axios instance for the billing API. Every failed request is rejected with an ApiError
// so callers get one shape whether the API answered, returned a non-JSON error, or was unreachable.
import axios, { AxiosError } from 'axios'
import { API_BASE_URL, API_KEY } from '../config'
import type { ApiErrorBody } from '../types/api'

/** Error raised for any failed API call; `code` is the API's error code or a client-side one. */
export class ApiError extends Error {
  readonly code: string
  readonly status: number | undefined
  readonly details: unknown[] | undefined

  constructor(code: string, message: string, status?: number, details?: unknown[]) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.details = details
  }
}

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'X-API-Key': API_KEY },
  timeout: 15_000,
})

function isApiErrorBody(body: unknown): body is ApiErrorBody {
  if (!body || typeof body !== 'object' || !('error' in body)) return false
  const { error } = body as { error: unknown }
  return !!error && typeof error === 'object' && 'code' in error && 'message' in error
}

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<unknown>) => {
    const body = error.response?.data
    if (isApiErrorBody(body)) {
      return Promise.reject(
        new ApiError(body.error.code, body.error.message, error.response?.status, body.error.details),
      )
    }
    if (error.response) {
      return Promise.reject(
        new ApiError('http_error', `Request failed with status ${error.response.status}`, error.response.status),
      )
    }
    return Promise.reject(new ApiError('network_error', 'Could not reach the API. Is the backend running?'))
  },
)

/** Human-readable message for anything thrown by a query or mutation. */
export function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  return 'Something went wrong'
}
