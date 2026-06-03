import fs from "fs";
import path from "path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const certDir = path.resolve(__dirname, "ssl");
const keyPath = path.join(certDir, "vite-localhost.key");
const certPath = path.join(certDir, "vite-localhost.crt");

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    https: {
      key: fs.readFileSync(keyPath),
      cert: fs.readFileSync(certPath),
    },
    proxy: {
      "/api": {
        target: "http://127.0.0.1:18000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://127.0.0.1:18000",
        ws: true,
        changeOrigin: true,
      },
    },
  },
});
