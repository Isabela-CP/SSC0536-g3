import react from '@vitejs/plugin-react'
import { createServer } from 'vite'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

export async function testServer() {
  // O cache de testes não interfere no servidor de desenvolvimento aberto.
  const cacheDir = await mkdtemp(join(tmpdir(), 'oto-vite-test-'))
  try {
    const server = await createServer({
      configFile: false,
      cacheDir,
      plugins: [react()],
      optimizeDeps: { noDiscovery: true, include: [] },
      server: { middlewareMode: true, ws: false },
      appType: 'custom',
    })
    const close = server.close.bind(server)
    server.close = async () => {
      try {
        await close()
      } finally {
        await rm(cacheDir, { recursive: true, force: true, maxRetries: 3, retryDelay: 50 })
      }
    }
    return server
  } catch (error) {
    await rm(cacheDir, { recursive: true, force: true, maxRetries: 3, retryDelay: 50 })
    throw error
  }
}
