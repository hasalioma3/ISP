import path from 'path'
import { fileURLToPath } from 'url'
import base from './isp-tailwind.cjs'

// Same theme as the ISP billing app (its tailwind.config.js), scanning this
// app plus the Savanna components it imports from there.
const here = path.dirname(fileURLToPath(import.meta.url))
const isp = path.resolve(here, process.env.ISP_FRONTEND_DIR || '../../frontend')

export default {
  ...base,
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
    path.join(isp, 'src/components/savanna/**/*.{ts,tsx}'),
    path.join(isp, 'src/components/ui/**/*.{ts,tsx}'),
  ],
}
