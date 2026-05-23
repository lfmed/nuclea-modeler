import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Construction } from "lucide-react";

interface PlaceholderPageProps {
  title: string;
  description: string;
  phase: "Fase 0" | "Fase 1" | "Fase 2" | "Fase 3";
  features: string[];
  moduleNumber: string;
}

export function PlaceholderPage({
  title,
  description,
  phase,
  features,
  moduleNumber,
}: PlaceholderPageProps) {
  const phaseColor =
    phase === "Fase 1"
      ? "bg-nuclea-primary text-primary-foreground"
      : phase === "Fase 2"
        ? "bg-amber-500 text-amber-950"
        : phase === "Fase 3"
          ? "bg-slate-500 text-slate-50"
          : "bg-emerald-500 text-emerald-950";

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
            <Badge variant="outline" className="font-mono">
              {moduleNumber}
            </Badge>
          </div>
          <p className="text-muted-foreground max-w-2xl">{description}</p>
        </div>
        <Badge className={phaseColor}>{phase}</Badge>
      </div>

      <Card className="border-dashed">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Construction className="h-5 w-5 text-nuclea-primary" />
            <CardTitle>Em construção</CardTitle>
          </div>
          <CardDescription>
            Esta página será entregue na <strong>{phase}</strong> conforme o plano militar.
            Veja <code>docs/prompts/01-plano-militar.md</code> no repositório.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <h3 className="text-sm font-semibold mb-3 text-muted-foreground uppercase tracking-wider">
            Funcionalidades planejadas
          </h3>
          <ul className="space-y-2">
            {features.map((feature, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <span className="mt-1.5 inline-block h-1.5 w-1.5 rounded-full bg-nuclea-primary shrink-0" />
                <span>{feature}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
