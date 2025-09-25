import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from "path"
import { visualizer } from 'rollup-plugin-visualizer'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    ...(process.env.ANALYZE_BUNDLE ? [visualizer({ filename: 'dist/bundle-stats.html', open: true })] : []),
  ],
  build: {
    // Raise limit to avoid noisy warnings while we improve chunking
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        // Split common vendor libs to keep app chunk smaller and improve caching
        manualChunks(id) {
          if (id.includes('node_modules')) {
// disabled react manual chunk
            if (id.includes('@radix-ui')) return 'vendor-radix'
            if (id.includes('lucide-react')) return 'vendor-icons'
            if (id.includes('wavesurfer.js')) return 'vendor-wavesurfer'
            if (id.includes('axios')) return 'vendor-axios'
            return 'vendor'
          }
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
  },
  // Force pre-bundling of wavesurfer to avoid intermittent resolution issues on Windows
  optimizeDeps: {
    include: [
  '@/vendor/wavesurfer.js',
  'wavesurfer.js/dist/wavesurfer.esm.js',
  'wavesurfer.js/dist/plugins/regions.esm.js'
    ]
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: '127.0.0.1', 
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      // Proxy static asset requests (audio, covers) to backend FastAPI server
      '/static': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
    // Add a fallback for HTML5 history API routing
    // This ensures that all non-API requests are served by index.html
    middleware: [
      (req, res, next) => {
        if (!req.url.startsWith('/api') && !req.url.includes('.')) {
          req.url = '/'; // Rewrite to root to serve index.html
        }
        next();
      },
    ],
  },
})