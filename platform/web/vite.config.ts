import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import fs from "node:fs";

// In dev, serve /library/* directly from the repo-root library/ folder so the
// React app can fetch index.json + per-story HTML without an API.
// In production, do the same via nginx — the platform is intentionally read-only
// over HTTP; writes (ingest, merge) happen via the Skill CLIs.
const LIBRARY_DIR = path.resolve(__dirname, "../../library");

export default defineConfig({
  plugins: [
    react(),
    {
      name: "serve-library",
      configureServer(server) {
        server.middlewares.use("/library", (req, res, next) => {
          // strip the /library prefix and resolve safely inside LIBRARY_DIR
          const rel = decodeURIComponent((req.url || "").split("?")[0]);
          const target = path.resolve(LIBRARY_DIR, "." + rel);
          if (!target.startsWith(LIBRARY_DIR)) {
            res.statusCode = 403;
            return res.end("Forbidden");
          }
          if (!fs.existsSync(target) || !fs.statSync(target).isFile()) {
            res.statusCode = 404;
            return res.end("Not found");
          }
          const ext = path.extname(target).toLowerCase();
          const types: Record<string, string> = {
            ".json": "application/json; charset=utf-8",
            ".html": "text/html; charset=utf-8",
            ".svg":  "image/svg+xml",
            ".jpg":  "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png":  "image/png",
            ".mp4":  "video/mp4",
            ".webm": "video/webm",
            ".mp3":  "audio/mpeg",
          };
          if (types[ext]) res.setHeader("Content-Type", types[ext]);
          fs.createReadStream(target).pipe(res);
        });
      },
    },
  ],
  server: { port: 5174, open: false },
});
