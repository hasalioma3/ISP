// Loads the ISP billing app's Tailwind config (an ES module that also uses
// require()) so this app shares its theme exactly. Kept in a .cjs shim
// because that file mixes module styles.
const path = require('path')
const fs = require('fs')
const isp = path.resolve(__dirname, process.env.ISP_FRONTEND_DIR || '../../frontend')
const src = fs.readFileSync(path.join(isp, 'tailwind.config.js'), 'utf8').replace('export default', 'module.exports =')
const m = { exports: {} }
// eslint-disable-next-line no-new-func
new Function('module', 'exports', 'require', src)(m, m.exports, require)
module.exports = m.exports
