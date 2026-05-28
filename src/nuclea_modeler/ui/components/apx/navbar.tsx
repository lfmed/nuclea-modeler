import { ModeToggle } from "@/components/apx/mode-toggle";
import Logo from "@/components/apx/logo";
import { Link } from "@tanstack/react-router";
import { HelpCircle } from "lucide-react";
import GlobalSearch from "@/components/apx/global-search";
import { ReactNode } from "react";

interface NavbarProps {
  leftContent?: ReactNode;
  rightContent?: ReactNode;
}

export function Navbar({ leftContent, rightContent }: NavbarProps) {
  return (
    <header role="banner" className="z-50 bg-background/80 backdrop-blur-sm border-b">
      <div className="h-16 flex items-center justify-between px-4">
        {leftContent || <Logo />}
        <div className="flex-1" />
        {rightContent || (
          <nav aria-label="Ações globais" className="flex items-center gap-2">
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
          </nav>
        )}
      </div>
    </header>
  );
}

export default Navbar;
