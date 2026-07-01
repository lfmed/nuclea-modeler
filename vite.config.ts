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
    // Carimbo de tempo do build da UI. Avaliado no momento do `vite build`
    // (roda em build-dist.yml no merge p/ main), então o rodapé mostra
    // exatamente quando o bundle deployado foi gerado. Ver ui/lib/build-info.ts.
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },
  build: {
    outDir: distDir,
    emptyOutDir: true,
    sourcemap: false,
    // Split heavy/independent vendor bundles so the initial route doesn't have
    // to download Monaco (used only on Code Objects) or XYFlow (only on DER).
    // TanStack Router already does per-route code splitting via the
    // autoCodeSplitting plugin option above.
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          if (id.includes("monaco-editor") || id.includes("@monaco-editor")) {
            return "vendor-monaco";
          }
          if (id.includes("@xyflow") || id.includes("@dagrejs/dagre")) {
            return "vendor-diagram";
          }
          if (id.includes("@tanstack/react-query") || id.includes("@tanstack/react-router")) {
            return "vendor-tanstack";
          }
          if (
            id.includes("/react/") ||
            id.includes("/react-dom/") ||
            id.includes("scheduler") ||
            id.includes("react-error-boundary")
          ) {
            return "vendor-react";
          }
          if (id.includes("@radix-ui/") || id.includes("lucide-react") || id.includes("class-variance-authority")) {
            return "vendor-ui";
          }
          if (id.includes("motion") || id.includes("html-to-image") || id.includes("sonner")) {
            return "vendor-misc";
          }
        },
      },
    },
    // Warn (don't fail) when an individual chunk goes over 600KB — gives a
    // visible signal during local builds.
    chunkSizeWarningLimit: 600,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
