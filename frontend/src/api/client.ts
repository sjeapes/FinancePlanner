import axios from 'axios'

/**
 * Compute an absolute API base URL from the current page location.
 *
 * Why not just '/api':
 *   '/api' is an absolute path — the browser resolves it against the origin
 *   (protocol + host). Through HA Ingress the page is served at
 *   https://ha.local/api/hassio_ingress/<token>/ but '/api/simulate' resolves
 *   to https://ha.local/api/simulate (the HA supervisor API, not the addon).
 *
 * How this works instead:
 *   We build an absolute URL by prepending protocol+host+pathname to '/api',
 *   giving e.g. https://ha.local/api/hassio_ingress/<token>/api.
 *   Axios then constructs https://ha.local/api/hassio_ingress/<token>/api/simulate
 *   for a request to '/simulate', which HA Ingress proxies correctly.
 *
 * Scenarios:
 *   HA Ingress   https://ha.local/api/hassio_ingress/<token>/  →  .../<token>/api
 *   Direct       http://192.168.1.x:8000/                      →  http://192.168.1.x:8000/api
 *   Dev (Vite)   http://localhost:5173/                         →  http://localhost:5173/api
 *                                                                  (Vite proxies /api/* to :8000)
 */
function getApiBase(): string {
  const { protocol, host, pathname } = window.location
  // Strip trailing slash so the joined URL doesn't get a double slash
  const base = pathname.replace(/\/+$/, '')
  return `${protocol}//${host}${base}/api`
}

export const apiClient = axios.create({
  baseURL: getApiBase(),
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
