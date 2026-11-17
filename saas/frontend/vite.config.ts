import path from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The ISP billing app's frontend, whose Savanna design system (tokens,
// components, formatting) this app imports instead of copying. `@` points at
// it so its own `@/lib/utils`-style imports keep working; this app's code is
// under `~`. In Docker it's copied to /app/isp-frontend (see Dockerfile).
const ISP_FRONTEND = path.resolve(__dirname, process.env.ISP_FRONTEND_DIR || '../../frontend')

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.join(ISP_FRONTEND, 'src'),
      '~': path.resolve(__dirname, './src'),
    },
    // Imported files live outside this project; make every shared package
    // resolve to ONE copy (this project's), or React would load twice.
    dedupe: ['react', 'react-dom', 'react-router-dom', 'lucide-react', 'clsx', 'tailwind-merge', 'recharts',
      'class-variance-authority', '@radix-ui/react-dialog', '@radix-ui/react-dropdown-menu', '@radix-ui/react-slot',
      'zustand', '@tanstack/react-query'],
  },
  server: {
    host: true,
    port: 5180,
    fs: { allow: [__dirname, ISP_FRONTEND] },
    proxy: { '/api': { target: 'http://127.0.0.1:8100', changeOrigin: true } },
  },
  build: { chunkSizeWarningLimit: 900 },
})
