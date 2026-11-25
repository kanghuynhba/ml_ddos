import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    // backend sends no CORS headers yet, so in dev the browser talks to /api and Vite forwards it
    server: {
      proxy: {
        "/api": { target: env.VITE_API_URL, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, "") },
      },
    },
  };
});
