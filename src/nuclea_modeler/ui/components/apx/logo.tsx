import { Link } from "@tanstack/react-router";

interface LogoProps {
  to?: string;
  className?: string;
  showText?: boolean;
}

export function Logo({ to = "/", className = "", showText = true }: LogoProps) {
  const content = (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <img
        src="/logo.svg"
        alt="Núclea Modeler"
        className="h-8 w-8 rounded-md shadow-sm"
      />
      {showText && (
        <div className="flex flex-col leading-tight">
          <span className="font-semibold text-base tracking-tight">Núclea Modeler</span>
          <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
            Data Catalog
          </span>
        </div>
      )}
    </div>
  );

  if (to) {
    return (
      <Link to={to} className="hover:opacity-80 transition-opacity">
        {content}
      </Link>
    );
  }

  return content;
}

export default Logo;
