import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  base: '/static/',
  plugins: [react()],
  server: {
    host: true,
    port: 80,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
    },
    allowedHosts: [
      'admin.hasalioma.online',
      'isp.hasalioma.online',
      'hasalioma.xyz',
      'api.hasalioma.xyz'
    ],
  },
})
