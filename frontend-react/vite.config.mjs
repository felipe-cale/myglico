import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = process.env.VITE_API_TARGET || "http://localhost:8001";

export default defineConfig(() => ({
  base: "/",
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 8000,
    strictPort: true,
    watch: {
      usePolling: true
    },
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true
      },
      "/artifacts": {
        target: apiTarget,
        changeOrigin: true
      },
      "/health": {
        target: apiTarget,
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: "client-build",
    emptyOutDir: true
  }
}));
