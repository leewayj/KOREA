import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('../', import.meta.url))
const apps = [
  { name: '사용자', directory: 'library-seat-web', port: 5173 },
  { name: '관리자', directory: 'library-seat-admin', port: 5174 },
]

// Check both installations before starting either server.
for (const app of apps) {
  app.cwd = path.join(root, app.directory)
  app.entry = path.join(app.cwd, 'node_modules/vite/bin/vite.js')
  if (!existsSync(app.entry)) {
    console.error(`${app.name} 앱의 의존성이 없습니다. KOREA 폴더에서 npm run install:all을 실행하세요.`)
    process.exit(1)
  }
}

const children = new Set()
let stopping = false
function stop(code = 0) {
  if (stopping) return
  stopping = true
  process.exitCode = code
  for (const child of children) child.kill('SIGTERM')
  // Do not leave a development server behind if shutdown stalls.
  const timer = setTimeout(() => {
    for (const child of children) child.kill('SIGKILL')
  }, 3000)
  timer.unref()
}
process.on('SIGINT', () => stop())
process.on('SIGTERM', () => stop())

for (const app of apps) {
  console.log(`${app.name} 페이지: http://127.0.0.1:${app.port}`)
  const child = spawn(process.execPath, [
    app.entry, '--host', '127.0.0.1', '--port', String(app.port), '--strictPort', '--clearScreen', 'false',
  ], { cwd: app.cwd, stdio: 'inherit' })
  children.add(child)
  child.on('error', error => {
    console.error(`${app.name} 서버를 실행하지 못했습니다: ${error.message}`)
    stop(1)
  })
  child.on('exit', code => {
    children.delete(child)
    if (!stopping) {
      console.error(`${app.name} 서버가 종료되어 두 서버를 함께 종료합니다.`)
      stop(code || 1)
    }
  })
}
console.log('Ctrl+C를 누르면 두 서버가 함께 종료됩니다.\n')
