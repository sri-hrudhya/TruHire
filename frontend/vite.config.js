import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// The backend can run on any host/port. Nothing is hardcoded here: tell the dev server where
// it is with ONE of these (in the root .env or inline in the shell):
//   VITE_BACKEND_URL=http://127.0.0.1:9001       full URL (any host, https allowed)
//   VITE_BACKEND_PORT=9001                        port only; host defaults to 127.0.0.1 (VITE_BACKEND_HOST to change)
// e.g.  VITE_BACKEND_PORT=9001 npm run dev
// The browser always calls the relative path /api, so this proxy is the only place that
// needs to know. Optionally pin the dev server port with VITE_PORT (default: Vite picks a free one).
function pick(env) {
  if (env.VITE_BACKEND_URL) return env.VITE_BACKEND_URL
  if (env.VITE_BACKEND_PORT) return `http://${env.VITE_BACKEND_HOST || '127.0.0.1'}:${env.VITE_BACKEND_PORT}`
  return null
}

// Shell variables win over .env, so the backend can be switched per run.
function resolveBackendUrl(fileEnv) {
  const url = pick(process.env) || pick(fileEnv)
  if (url) return url
  throw new Error(
    'Backend address not configured. Set VITE_BACKEND_URL (e.g. http://127.0.0.1:9001) or VITE_BACKEND_PORT ' +
    'in frontend/.env, or run:  VITE_BACKEND_PORT=<port> npm run dev'
  )
}

export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, process.cwd(), ''), ...process.env }
  const isDev = mode === 'development'
  const backendUrl = isDev ? resolveBackendUrl(loadEnv(mode, process.cwd(), '')) : undefined

  return {
    plugins: [react()],
    server: {
      ...(env.VITE_PORT ? { port: Number(env.VITE_PORT) } : {}),
      proxy: backendUrl
        ? { '/api': { target: backendUrl, changeOrigin: true } }
        : undefined,
    },
  }
})
