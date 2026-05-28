import { ThemeProvider } from "@/components/apx/theme-provider";
import { WelcomeTour } from "@/components/apx/welcome-tour";
import { QueryClient } from "@tanstack/react-query";
import { createRootRouteWithContext, Outlet } from "@tanstack/react-router";
import { Toaster } from "sonner";

export const Route = createRootRouteWithContext<{
  queryClient: QueryClient;
}>()({
  component: () => (
    <ThemeProvider defaultTheme="dark" storageKey="apx-ui-theme">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[100] focus:px-3 focus:py-2 focus:rounded-md focus:bg-primary focus:text-primary-foreground focus:shadow-lg"
      >
        Pular para o conteúdo principal
      </a>
      <Outlet />
      <WelcomeTour />
      <Toaster richColors />
    </ThemeProvider>
  ),
});
