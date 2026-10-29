import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// The ONLY frontend env var is VITE_DEV_BACKEND_URL (a non-secret URL used by the
// dev proxy). Never put tokens, passwords or API keys in VITE_* variables:
// they are bundled into public JavaScript.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backend = env.VITE_DEV_BACKEND_URL || "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        "/api": { target: backend, changeOrigin: false },
        "/health": { target: backend, changeOrigin: false },
      },
    },
    preview: { port: 5173 },
  };
});
