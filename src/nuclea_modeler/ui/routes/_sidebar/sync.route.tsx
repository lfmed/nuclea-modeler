import { createFileRoute, Outlet } from "@tanstack/react-router";

// Layout pai puro — força TanStack Router a usar este como wrapper de
// sync.index.tsx e sync.$id.tsx (ou novos siblings). Sem isso, o
// plugin file-based promovia o componente da .index.tsx para parent layout
// e o detail nunca conseguia renderizar dentro.
export const Route = createFileRoute("/_sidebar/sync")({
  component: () => <Outlet />,
});
