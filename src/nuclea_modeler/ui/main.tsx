import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@/styles/globals.css";
import { routeTree } from "@/types/routeTree.gen";
import { NotFoundPage } from "@/components/apx/not-found";

import { RouterProvider, createRouter } from "@tanstack/react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ─── Auto-reload on stale chunk ────────────────────────────────────────────
// When the user's tab has the old index.html in memory but the server has
// deployed new chunks (with new hashes), dynamic imports fail with a
// "Failed to fetch dynamically imported module" or similar. We catch that
// and force-reload to fetch the fresh HTML.
const STALE_CHUNK_MARKERS = [
  "Failed to fetch dynamically imported module",
  "error loading dynamically imported module",
  "Importing a module script failed",
  "ChunkLoadError",
];
function shouldReloadFromError(err: unknown): boolean {
  const msg = err instanceof Error ? err.message : String(err);
  return STALE_CHUNK_MARKERS.some((m) => msg.includes(m));
}
function tryReloadIfStale(err: unknown) {
  if (!shouldReloadFromError(err)) return;
  // Guard against reload loops: only reload once per session
  const flag = "__nuclea_reloaded_once__";
  if (sessionStorage.getItem(flag)) return;
  sessionStorage.setItem(flag, "1");
  console.warn("[Núclea Modeler] Stale chunk detected, reloading…", err);
  window.location.reload();
}
window.addEventListener("error", (e) => tryReloadIfStale(e.error || e.message));
window.addEventListener("unhandledrejection", (e) => tryReloadIfStale(e.reason));

// Create a new query client instance
const queryClient = new QueryClient();

const router = createRouter({
  routeTree,
  context: {
    queryClient,
  },
  defaultPreload: "intent",
  // Since we're using React Query, we don't want loader calls to ever be stale
  // This will ensure that the loader is always called when the route is preloaded or visited
  defaultPreloadStaleTime: 0,
  scrollRestoration: true,
  defaultErrorComponent: ({ error, reset }) => {
    console.error("[Núclea Modeler] Route error:", error);
    return (
      <div style={{ padding: "2rem", fontFamily: "system-ui" }}>
        <h2 style={{ color: "#b91c1c", marginBottom: "1rem" }}>
          Erro ao carregar a página
        </h2>
        <pre
          style={{
            background: "#fee2e2",
            padding: "1rem",
            borderRadius: 8,
            overflow: "auto",
            fontSize: 12,
          }}
        >
          {error instanceof Error ? `${error.name}: ${error.message}\n${error.stack ?? ""}` : String(error)}
        </pre>
        <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem" }}>
          <button onClick={() => reset()} style={{ padding: "0.5rem 1rem", border: "1px solid #ccc", borderRadius: 6 }}>
            Tentar novamente
          </button>
          <button onClick={() => window.location.reload()} style={{ padding: "0.5rem 1rem", border: "1px solid #ccc", borderRadius: 6 }}>
            Recarregar
          </button>
        </div>
      </div>
    );
  },
  defaultPendingComponent: () => (
    <div style={{ padding: "2rem", textAlign: "center", color: "#6b7280" }}>
      Carregando…
    </div>
  ),
  defaultNotFoundComponent: () => <NotFoundPage />,
});

// Register things for typesafety
declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

const rootElement = document.getElementById("root")!;

if (!rootElement.innerHTML) {
  const root = createRoot(rootElement);
  root.render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </StrictMode>,
  );
}
