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
    <header className="z-50 bg-background/80 backdrop-blur-sm border-b">
      <div className="h-16 flex items-center justify-between px-4">
        {leftContent || <Logo />}
        <div className="flex-1" />
        {rightContent || (
          <div className="flex items-center gap-2">
            <GlobalSearch />
            <Link
              to="/help"
              title="Ajuda"
              aria-label="Ajuda"
              className="inline-flex items-center justify-center rounded-md size-9 text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
            >
              <HelpCircle className="h-4 w-4" />
            </Link>
            <ModeToggle />
          </div>
        )}
      </div>
    </header>
  );
}

export default Navbar;
