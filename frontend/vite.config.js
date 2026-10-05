import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { naradAuthProxy, naradAuthStatusPlugin } from './naradDevAuth.js';

// Local backend that the dev/preview server proxies /api to.
const NARAD_BACKEND_URL = 'http://127.0.0.1:8000';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), naradAuthStatusPlugin()],
  server: {
    port: 5173,
    proxy: {
      // Authenticated server-side with NARAD_API_KEY from backend/.env (see naradDevAuth.js).
      '/api': naradAuthProxy(NARAD_BACKEND_URL),
    },
  },
  preview: {
    proxy: {
      '/api': naradAuthProxy(NARAD_BACKEND_URL),
    },
  },
});
