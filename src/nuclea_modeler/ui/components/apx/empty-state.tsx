import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  description?: ReactNode;
  primaryAction?: {
    label: string;
    /** Either `to` (router link) or `onClick` (handler). */
    to?: string;
    onClick?: () => void;
  };
  secondaryAction?: {
    label: string;
    to?: string;
    onClick?: () => void;
  };
  className?: string;
}

/**
 * Empty state card with illustration slot, copy and one or two CTAs.
 *
 * Usage:
 *   <EmptyState
 *     icon={<Database className="h-10 w-10" />}
 *     title="Nenhuma conexão cadastrada"
 *     description="Conexões representam ambientes (HINT/HEXT/PROD) catalogados pelo app."
 *     primaryAction={{ label: "Nova conexão", to: "/connections/new" }}
 *     secondaryAction={{ label: "Ajuda", to: "/help" }}
 *   />
 */
export function EmptyState({
  icon,
  title,
  description,
  primaryAction,
  secondaryAction,
  className,
}: EmptyStateProps) {
  return (
    <Card className={cn("border-dashed bg-muted/20", className)}>
      <CardContent className="flex flex-col items-center text-center py-16 px-6">
        <div
          aria-hidden="true"
          className="mb-6 flex h-20 w-20 items-center justify-center rounded-2xl bg-gradient-to-br from-primary/15 to-accent/15 text-primary"
        >
          {icon}
        </div>
        <h3 className="text-lg font-semibold mb-2">{title}</h3>
        {description && (
          <div className="text-sm text-muted-foreground max-w-md mb-6">
            {description}
          </div>
        )}
        {(primaryAction || secondaryAction) && (
          <div className="flex flex-wrap gap-3 justify-center">
            {primaryAction && (
              primaryAction.to ? (
                <Button asChild>
                  <Link to={primaryAction.to}>{primaryAction.label}</Link>
                </Button>
              ) : (
                <Button onClick={primaryAction.onClick}>
                  {primaryAction.label}
                </Button>
              )
            )}
            {secondaryAction && (
              secondaryAction.to ? (
                <Button asChild variant="outline">
                  <Link to={secondaryAction.to}>{secondaryAction.label}</Link>
                </Button>
              ) : (
                <Button variant="outline" onClick={secondaryAction.onClick}>
                  {secondaryAction.label}
                </Button>
              )
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default EmptyState;
