import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    tailwindcss(),
    react()
  ],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    // src/lib 下的测试为 node:test 风格（node --test 运行），vitest 不接管
    exclude: ['**/node_modules/**', '**/dist/**', 'src/lib/**'],
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return undefined;
          }
          if (id.includes('recharts')) {
            return 'charts-vendor';
          }
          if (id.includes('react') || id.includes('scheduler')) {
            return 'react-vendor';
          }
          if (id.includes('framer-motion')) {
            return 'motion-vendor';
          }
          // PDF 导出栈（html2pdf 动态导入链路）单独成 chunk，避免被入口静态引用
          if (['html2pdf.js', 'html2canvas', 'jspdf', 'canvg', 'stackblur-canvas', 'pako', 'fflate'].some(k => id.includes(k))) {
            return 'pdf-vendor';
          }
          // 其余依赖交给 Rollup 自动分割，不再堆积到单一 vendor
          return undefined;
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8085',
        changeOrigin: true,
      },
    },
  },
})
