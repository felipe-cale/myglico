import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = process.env.VITE_API_TARGET || "http://localhost:8001";

export default defineConfig(() => ({
  base: "/",
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // recharts and its d3 dependencies only serve the patient detail charts. React and the
        // other app-wide libraries get their own chunk so rollup never hoists them into "recharts"
        // (which would make the entry, and every public page, preload the charts).
        manualChunks(id) {
          if (/node_modules[\\/](recharts|recharts-scale|victory-vendor|d3-[^\\/]+|internmap|decimal\.js-light|lodash|eventemitter3|react-smooth|fast-equals|tiny-invariant|clsx)[\\/]/.test(id)) return "recharts";
          if (id.includes("commonjsHelpers") || /node_modules[\\/](react|react-dom|react-is|scheduler|react-router|react-router-dom|@remix-run|i18next|react-i18next|html-parse-stringify|void-elements|use-sync-external-store|prop-types|object-assign)[\\/]/.test(id)) return "vendor";
          return undefined;
        }
      }
    }
  },
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
  }
}));
