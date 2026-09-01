import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiPrefix = env.VITE_API_BASE_URL || "/api/ragent";
  const proxyTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:9090";

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(import.meta.dirname, "./src"),
      },
    },
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: {
        [apiPrefix]: {
          target: proxyTarget,
          changeOrigin: true,
          rewrite: (requestPath) => requestPath.replace(new RegExp(`^${apiPrefix}`), ""),
        },
      },
    },
  };
});
