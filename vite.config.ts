import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Vite config for the Núclea Modeler UI.
 *
 * Hand-written (apx build is skipped — corp network blocks pypi/npm locally).
 *
 * Layout:
 *   src/nuclea_modeler/ui/        ← Vite "root" (where index.html + main.tsx live)
 *   src/nuclea_modeler/__dist__/  ← build output, served by FastAPI as static
 *
 * All TanStack Router paths are ABSOLUTE so they don't get re-resolved
 * relative to the changing Vite root.
 */
const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.dirname(__filename);
const uiDir = path.resolve(projectRoot, "src/nuclea_modeler/ui");
const distDir = path.resolve(projectRoot, "src/nuclea_modeler/__dist__");

export default defineConfig({
  root: uiDir,
  base: "/",
  plugins: [
    TanStackRouterVite({
      routesDirectory: path.join(uiDir, "routes"),
      generatedRouteTree: path.join(uiDir, "types/routeTree.gen.ts"),
      autoCodeSplitting: true,
    }),
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      "@": uiDir,
    },
  },
  define: {
    __APP_NAME__: JSON.stringify("Núclea Modeler"),
  },
  build: {
    outDir: distDir,
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
