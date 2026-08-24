import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  // base: './' produces relative asset paths in the built HTML:
  //   <script src="./assets/main.js"> instead of <script src="/assets/main.js">
  //
  // This is required for HA Ingress, where the page is served at a prefix path
  // like /api/hassio_ingress/<token>/. Absolute paths (/assets/*) resolve
  // against the HA host and miss the addon completely.
  //
  // Relative paths resolve against the current page URL, so they go through
  // the same Ingress proxy regardless of the prefix. Also safe for direct
  // access (http://addon:8000/) and the Vite dev server (http://localhost:5173/).
  base: './',

  plugins: [react(), tailwindcss()],

  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
