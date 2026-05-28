import { Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useTheme } from "@/components/apx/theme-provider";

export function ModeToggle() {
  const { theme, setTheme } = useTheme();

  const toggleTheme = () => {
    setTheme(theme === "light" ? "dark" : "light");
  };

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggleTheme}
      aria-label={theme === "light" ? "Mudar para tema escuro" : "Mudar para tema claro"}
      aria-pressed={theme === "dark"}
      className="w-8 h-8 p-2 rounded-sm transition-transform duration-200 ease-in-out hover:scale-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
    >
      {theme === "light" ? (
        <Sun aria-hidden="true" className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
      ) : (
        <Moon aria-hidden="true" className="rotate-90 h-4 w-4 scale-0 transition-all dark:rotate-0 dark:scale-100" />
      )}
      <span className="sr-only">Alternar tema</span>
    </Button>
  );
}
