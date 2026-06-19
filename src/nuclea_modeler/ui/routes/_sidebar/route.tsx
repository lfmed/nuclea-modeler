import SidebarLayout from "@/components/apx/sidebar-layout";
import { createFileRoute, Link, useLocation } from "@tanstack/react-router";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Database,
  ScanSearch,
  FileText,
  Tags,
  BookOpenText,
  GitFork,
  History,
  CloudCog,
  FileCode,
  Link2,
  Network,
  FolderTree,
  TestTube2,
  User,
  Inbox,
  Shield,
  HelpCircle,
  Code2,
  Activity,
  Gauge,
} from "lucide-react";
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

export const Route = createFileRoute("/_sidebar")({
  component: () => <Layout />,
});

type NavItem = {
  to: string;
  label: string;
  icon: React.ReactNode;
  match: (path: string) => boolean;
};

type NavSection = {
  label: string;
  items: NavItem[];
};

function Layout() {
  const location = useLocation();

  const sections: NavSection[] = [
    {
      label: "Visão Geral",
      items: [
        {
          to: "/dashboard",
          label: "Dashboard",
          icon: <LayoutDashboard size={16} />,
          match: (p) => p.startsWith("/dashboard"),
        },
      ],
    },
    {
      label: "Modelagem",
      items: [
        {
          to: "/explorer",
          label: "Navegador",
          icon: <FolderTree size={16} />,
          match: (p) => p.startsWith("/explorer"),
        },
        {
          to: "/diagram",
          label: "Diagrama (DER)",
          icon: <Network size={16} />,
          match: (p) => p.startsWith("/diagram"),
        },
        {
          to: "/entities",
          label: "Entidades",
          icon: <FileText size={16} />,
          match: (p) => p.startsWith("/entities"),
        },
        {
          to: "/relationships",
          label: "Relacionamentos",
          icon: <Link2 size={16} />,
          match: (p) => p.startsWith("/relationships"),
        },
      ],
    },
    {
      label: "Fontes & Código",
      items: [
        {
          to: "/connections",
          label: "Conexões",
          icon: <Database size={16} />,
          match: (p) => p.startsWith("/connections"),
        },
        {
          to: "/extractions",
          label: "Engenharia Reversa",
          icon: <ScanSearch size={16} />,
          match: (p) => p.startsWith("/extractions"),
        },
        {
          to: "/code",
          label: "Código DB",
          icon: <Code2 size={16} />,
          match: (p) => p.startsWith("/code"),
        },
      ],
    },
    {
      label: "Governança",
      items: [
        {
          to: "/flags",
          label: "Flags & LGPD",
          icon: <Tags size={16} />,
          match: (p) => p.startsWith("/flags"),
        },
        {
          to: "/glossary",
          label: "Dicionário",
          icon: <BookOpenText size={16} />,
          match: (p) => p.startsWith("/glossary"),
        },
        {
          to: "/lineage",
          label: "Linhagem",
          icon: <GitFork size={16} />,
          match: (p) => p.startsWith("/lineage"),
        },
        {
          to: "/versions",
          label: "Versões",
          icon: <History size={16} />,
          match: (p) => p.startsWith("/versions"),
        },
      ],
    },
    {
      label: "Operações",
      items: [
        {
          to: "/sync",
          label: "Sync Unity Catalog",
          icon: <CloudCog size={16} />,
          match: (p) => p.startsWith("/sync"),
        },
        {
          to: "/ddl",
          label: "Exportar DDL",
          icon: <FileCode size={16} />,
          match: (p) => p.startsWith("/ddl"),
        },
        {
          to: "/lakebase",
          label: "Lakebase Sandbox",
          icon: <TestTube2 size={16} />,
          match: (p) => p.startsWith("/lakebase"),
        },
      ],
    },
    {
      label: "Aprovações",
      items: [
        {
          to: "/tickets",
          label: "Tickets",
          icon: <Inbox size={16} />,
          match: (p) => p.startsWith("/tickets"),
        },
      ],
    },
    {
      label: "Conta",
      items: [
        {
          to: "/help",
          label: "Ajuda",
          icon: <HelpCircle size={16} />,
          match: (p) => p.startsWith("/help"),
        },
        {
          to: "/profile",
          label: "Perfil",
          icon: <User size={16} />,
          match: (p) => p === "/profile",
        },
        {
          to: "/admin/roles",
          label: "Papéis (RBAC)",
          icon: <Shield size={16} />,
          match: (p) => p.startsWith("/admin/roles"),
        },
        {
          to: "/admin/audit",
          label: "Auditoria",
          icon: <Activity size={16} />,
          match: (p) => p.startsWith("/admin/audit"),
        },
        {
          to: "/admin/metrics",
          label: "Métricas",
          icon: <Gauge size={16} />,
          match: (p) => p.startsWith("/admin/metrics"),
        },
      ],
    },
  ];

  return (
    <SidebarLayout>
      {sections.map((section) => (
        <SidebarGroup key={section.label}>
          <SidebarGroupLabel>{section.label}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {section.items.map((item) => (
                <SidebarMenuItem key={item.to}>
                  <Link
                    to={item.to}
                    className={cn(
                      "flex items-center gap-2 p-2 rounded-lg text-sm transition-colors",
                      item.match(location.pathname)
                        ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                        : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                    )}
                  >
                    {item.icon}
                    <span>{item.label}</span>
                  </Link>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      ))}
    </SidebarLayout>
  );
}
