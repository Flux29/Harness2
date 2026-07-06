import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev mode proxies same-origin /agent to the backend, so the SAME relative
// URL works in `npm run dev` (:3000) and in the built app served by FastAPI.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/agent": "http://localhost:8801",
      "/threads": "http://localhost:8801",
    },
  },
});
