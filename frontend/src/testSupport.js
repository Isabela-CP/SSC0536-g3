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
      cacheDir,
      plugins: [react()],
      server: { middlewareMode: true, ws: false },
      appType: 'custom',
    })
    const close = server.close.bind(server)
    server.close = async () => {
      try {
        await close()
      } finally {
        await rm(cacheDir, { recursive: true, force: true })
      }
    }
    return server
  } catch (error) {
    await rm(cacheDir, { recursive: true, force: true })
    throw error
  }
}
