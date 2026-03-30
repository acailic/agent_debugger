import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiPort = process.env.API_PORT || '8000'

export default defineConfig({
  plugins: [react()],
  base: "/ui/",
  define: {
    __BUNDLED_DEV__: false,
    __SERVER_FORWARD_CONSOLE__: false
  },
  server: {
    port: 3000,
    proxy: {
      '/api': `http://localhost:${apiPort}`
    }
  }
})
