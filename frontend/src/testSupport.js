import react from '@vitejs/plugin-react'
import { createServer } from 'vite'
export const testServer = () => createServer({ plugins: [react()], server: { middlewareMode: true, ws: false }, appType: 'custom' })
