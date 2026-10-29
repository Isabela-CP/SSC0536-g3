import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import react from '@vitejs/plugin-react'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

describe('App', () => {
  let server

  before(async () => {
    server = await createServer({
      plugins: [react()],
      server: { middlewareMode: true },
      appType: 'custom',
    })
  })

  after(async () => {
    await server?.close()
  })

  it('deve renderizar o título principal OTO Hospedagem', async () => {
    const { default: App } = await server.ssrLoadModule('/src/App.jsx')
    const html = renderToStaticMarkup(React.createElement(App))

    assert.match(html, /<h1>OTO Hospedagem<\/h1>/)
  })
})
