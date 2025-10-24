import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from "path"
import { visualizer } from 'rollup-plugin-visualizer'

// Chunk load retry plugin - handles stale chunk errors after deployments
function chunkLoadRetryPlugin() {
  return {
    name: 'chunk-load-retry',
    async buildEnd() {
      // No-op at build time
    },
    transformIndexHtml() {
      return [
        {
          tag: 'script',
          injectTo: 'head-prepend',
          children: `
            // Detect chunk load failures and retry with cache bust
            const originalImport = window.__vite_dynamic_import__;
            if (originalImport) {
              window.__vite_dynamic_import__ = async (id) => {
                try {
                  return await originalImport(id);
                } catch (error) {
                  // Check if this is a chunk load failure
                  if (error?.message?.includes('Failed to fetch dynamically imported module')) {
                    console.warn('[Chunk Retry] Stale chunk detected, reloading page...');
                    // Force hard reload to get fresh HTML with new chunk hashes
                    window.location.reload();
                    // Return a never-resolving promise to prevent further errors
                    return new Promise(() => {});
                  }
                  throw error;
                }
              };
            }
          `,
        },
      ];
    },
  };
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    chunkLoadRetryPlugin(),
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