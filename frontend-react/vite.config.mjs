import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = process.env.VITE_API_TARGET || "http://localhost:8001";
// Temporary tunnels (phone testing) are allowed only through an explicit, comma-separated list.
const allowedHosts = process.env.VITE_ALLOWED_HOSTS ? process.env.VITE_ALLOWED_HOSTS.split(",").map((host) => host.trim()).filter(Boolean) : undefined;

const proxy = {
    "/api": {
      target: apiTarget,
      // Host must stay the browser's: /api/glico validates Origin against the request host (CSRF).
      changeOrigin: false,
      // Phone-testing tunnels end TLS before this server: tell the API which scheme the browser
      // really used (https through an allowed tunnel host, http for direct local access).
      ...(process.env.VITE_TUNNEL_HTTPS ? {
        configure(proxy) {
          proxy.on("proxyReq", (proxyReq, req) => {
            const host = String(req.headers.host || "").split(":")[0].toLowerCase();
            const tunneled = (allowedHosts || []).some((entry) => entry.startsWith(".") ? host.endsWith(entry) : host === entry);
            proxyReq.setHeader("x-forwarded-proto", tunneled ? "https" : "http");
          });
        }
      } : {})
    },
    "/artifacts": {
      target: apiTarget,
      changeOrigin: true
    },
    "/health": {
      target: apiTarget,
      changeOrigin: true
    }
  };

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
    ...(allowedHosts ? { allowedHosts } : {}),
    watch: {
      usePolling: true
    },
    proxy
  },
  // `vite preview` serves the compiled app: no hot-reload websocket, so a tablet that leaves the
  // browser for the camera is not reloaded when it comes back (the dev server does exactly that).
  preview: {
    host: "0.0.0.0",
    port: 8000,
    strictPort: true,
    ...(allowedHosts ? { allowedHosts } : {}),
    proxy
  }
}));
