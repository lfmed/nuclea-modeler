import { Link, Outlet } from "@tanstack/react-router";
import type { ReactNode } from "react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarInset,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import SidebarUserFooter from "@/components/apx/sidebar-user-footer";
import { APP_VERSION, formatBuildTime } from "@/lib/build-info";
import { ModeToggle } from "@/components/apx/mode-toggle";
import Logo from "@/components/apx/logo";
import { HelpCircle } from "lucide-react";
import GlobalSearch from "@/components/apx/global-search";

interface SidebarLayoutProps {
  children?: ReactNode;
}

function SidebarLayout({ children }: SidebarLayoutProps) {
  return (
    <SidebarProvider>
      <Sidebar>
        <SidebarHeader>
          <div className="px-2 py-2">
            <Logo />
          </div>
        </SidebarHeader>
        <SidebarContent>{children}</SidebarContent>
        <SidebarFooter>
          <SidebarUserFooter />
          {/* Versão + data/hora do build — visibilidade do que está deployado
              no cliente vs. a última versão. Incrementar APP_VERSION a cada
              melhoria (ver ui/lib/build-info.ts). */}
          <div
            className="px-2 pb-1 text-[10px] leading-tight text-muted-foreground group-data-[collapsible=icon]:hidden"
            title={`Build: ${formatBuildTime()}`}
          >
            <span className="font-mono">v{APP_VERSION}</span>
            <span className="mx-1">·</span>
            <span>build {formatBuildTime()}</span>
          </div>
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>
      <SidebarInset className="flex flex-col h-screen">
        <header
          role="banner"
          className="sticky top-0 z-50 bg-background/80 backdrop-blur-sm border-b flex h-16 shrink-0 items-center gap-2 px-4"
        >
          <SidebarTrigger
            className="-ml-1 cursor-pointer"
            aria-label="Alternar visibilidade da barra lateral"
          />
          <div className="flex-1" />
          <GlobalSearch />
          <Link
            to="/help"
            title="Ajuda"
            aria-label="Abrir centro de ajuda"
            className="inline-flex items-center justify-center rounded-md size-9 text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
          >
            <HelpCircle className="h-4 w-4" aria-hidden="true" />
          </Link>
          <ModeToggle />
        </header>
        <main
          id="main-content"
          role="main"
          className="flex flex-1 justify-center overflow-auto"
        >
          <div className="flex flex-1 flex-col gap-4 p-6 max-w-7xl">
            <Outlet />
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
export default SidebarLayout;
