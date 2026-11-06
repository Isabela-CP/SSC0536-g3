import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { test } from 'node:test'
import { backendProxy } from '../devProxy.js'
import { viteConfigFor } from '../vite.config.js'

test('proxy encaminha API e preserva query string e multipart', () => {
  const proxy = backendProxy({ OTO_API_TARGET: 'http://127.0.0.1:8000' })
  assert.equal(proxy.target, 'http://127.0.0.1:8000')
  assert.equal(proxy.rewrite('/api/estabelecimentos?page=2'), '/estabelecimentos?page=2')
  assert.equal(
    proxy.rewrite('/api/estabelecimentos/id/documentos'),
    '/estabelecimentos/id/documentos',
  )
  assert.equal(proxy.rewrite('/apiculture'), '/apiculture')
  assert.equal(proxy.configure, undefined)
})

test('Bearers locais são opcionais e não substituem a sessão autenticada', () => {
  const proxy = new EventEmitter()
  const calls = []
  const request = { setHeader: (...args) => calls.push(args) }
  backendProxy({ OTO_DEV_BEARER_TOKEN: 'local-token' }).configure(proxy)
  proxy.emit('proxyReq', request, { headers: {} })
  assert.deepEqual(calls, [['Authorization', 'Bearer local-token']])
  calls.length = 0
  proxy.emit('proxyReq', request, { headers: { authorization: 'Bearer user-token' } })
  assert.deepEqual(calls, [])
  assert.equal(backendProxy({ OTO_DEV_BEARER_TOKEN: '  ' }).configure, undefined)
})

test('build de produção não recebe o proxy nem credenciais de desenvolvimento', () => {
  const config = viteConfigFor('build', { OTO_DEV_BEARER_TOKEN: 'local-private-token' })
  assert.equal(config.server, undefined)
  assert.equal(JSON.stringify(config).includes('local-private-token'), false)
  assert.ok(viteConfigFor('serve').server.proxy['/api'])
})
