import { defineConfig } from "vite";
export default defineConfig({
  server: {
    proxy: {
      "/api": "http://127.0.0.1:5190",
      "/agent": "http://127.0.0.1:5190",
    },
  },
});
