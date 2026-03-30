import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

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
      '/api': 'http://localhost:8001'
    }
  }
})
