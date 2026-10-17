/**
 * System Role: Vite build & dev-server configuration for the React frontend.
 * Inputs: VITE_DEV_PROXY_TARGET from frontend/.env (dev only).
 * Outputs: Production bundle in dist/; dev server proxying /api -> Node.js API Gateway (SSE-safe).
 */
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "VITE_");
  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": {
          target: env.VITE_DEV_PROXY_TARGET || "http://localhost:3000",
          changeOrigin: true,
        },
      },
    },
  };
});
