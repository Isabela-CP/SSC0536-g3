import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { backendProxy } from './devProxy.js'

export function viteConfigFor(command, env = {}) {
  return {
    plugins: [react()],
    ...(command === 'serve' ? { server: { proxy: { '/api': backendProxy(env) } } } : {}),
  }
}

export default defineConfig(({ command, mode }) =>
  viteConfigFor(command, loadEnv(mode, process.cwd(), '')),
)
