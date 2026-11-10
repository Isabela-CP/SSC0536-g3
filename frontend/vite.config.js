import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { backendProxy } from './devProxy.js'

export function viteConfigFor(command, env = {}) {
  return {
    base: env.VITE_BASE_PATH || '/',
    plugins: [react()],
    ...(command === 'serve' ? { server: { proxy: { '/api': backendProxy(env) } } } : {}),
  }
}

export default defineConfig(({ command, mode }) =>
  viteConfigFor(command, loadEnv(mode, process.cwd(), '')),
)
