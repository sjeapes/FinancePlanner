import axios from 'axios'

export const apiClient = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

apiClient.interceptors.response.use(
  (r) => r,
  (err: unknown) => {
    if (axios.isAxiosError(err)) {
      console.error('[LifeLedger API Error]', err.response?.data ?? err.message)
    } else {
      console.error('[LifeLedger API Error]', err)
    }
    return Promise.reject(err)
  }
)
