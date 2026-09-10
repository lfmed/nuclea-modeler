/**
 * Calendário de avaliação de conformidade (rodada 8, item 3).
 *
 * Lista os agendamentos por sistema (periodicidade + próxima data), permite a 1ª
 * carga via planilha (CSV/XLSX), cadastro manual e "Registrar execução" (grava e
 * avança a próxima data). O pop-up de lembrete é o componente ComplianceReminder,
 * montado no layout da sidebar. A execução da avaliação em si é FORA do app; o
 * checklist pode ser anexado ao sistema (módulo de Anexos).
 */
import { createFileRoute } from "@tanstack/react-router";
import { Suspense, useRef, useState } from "react";
import { QueryErrorResetBoundary, useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { toast } from "sonner";

import {
  useListComplianceSchedulesSuspense,
  useUpsertComplianceSchedule,
  useExecuteComplianceSchedule,
  useDeleteComplianceSchedule,
  useImportComplianceCalendar,
  useListSystemsSuspense,
  type ComplianceScheduleOut,
  type Recurrence,
  type SystemListOut,
} from "@/lib/api";
import selector from "@/lib/selector";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, CalendarCheck, Upload, CheckCircle2, Trash2, Clock } from "lucide-react";

export const Route = createFileRoute("/_sidebar/compliance")({
  component: CompliancePage,
});

/** Rótulos PT das periodicidades (o backend guarda a chave canônica). */
export const RECURRENCE_LABEL: Record<Recurrence, string> = {
  MONTHLY: "Mensal",
  QUARTERLY: "Trimestral",
  SEMIANNUAL: "Semestral",
  ANNUAL: "Anual",
};

function CompliancePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
          <CalendarCheck className="h-7 w-7 text-nuclea-primary" />
          Conformidade
        </h1>
        <p className="text-muted-foreground">
          Calendário de avaliação de conformidade por sistema. O app calcula as próximas
          datas e avisa quando vencerem; a avaliação em si é executada fora do Núclea Modeler
          (anexe o checklist ao sistema, se quiser).
        </p>
      </div>

      <QueryErrorResetBoundary>
        {({ reset }) => (
          <ErrorBoundary
            onReset={reset}
            fallbackRender={({ resetErrorBoundary }) => (
              <Card className="border-destructive/50">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-destructive">
                    <AlertCircle className="h-5 w-5" />
                    Erro ao carregar o calendário
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Button onClick={resetErrorBoundary}>Tentar novamente</Button>
                </CardContent>
              </Card>
            )}
          >
            <Suspense fallback={<Skeleton className="h-64 w-full" />}>
              <ComplianceContent />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    </div>
  );
}

function ComplianceContent() {
  const { data: schedules } = useListComplianceSchedulesSuspense({}, selector());
  const { data: systems } = useListSystemsSuspense(selector());
  const qc = useQueryClient();

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["listComplianceSchedules"] });
    qc.invalidateQueries({ queryKey: ["complianceDue"] });
  };

  return (
    <div className="space-y-6">
      <div className="grid gap-6 md:grid-cols-2">
        <ImportCard onDone={invalidate} />
        <ManualAddCard systems={systems as SystemListOut[]} onDone={invalidate} />
      </div>
      <SchedulesTable schedules={schedules} onChanged={invalidate} />
    </div>
  );
}

function ImportCard({ onDone }: { onDone: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const { mutate: importFile, isPending } = useImportComplianceCalendar({
    mutation: {
      onSuccess: (r) => {
        onDone();
        toast.success(
          `Importado: ${r.imported} novo(s), ${r.updated} atualizado(s), ${r.failed} com erro`,
          {
            description:
              r.failed > 0
                ? r.rows.filter((x) => !x.ok).slice(0, 3).map((x) => `${x.system}: ${x.error}`).join(" · ")
                : undefined,
          },
        );
        if (fileRef.current) fileRef.current.value = "";
      },
      onError: (e) => toast.error("Falha ao importar", { description: String(e) }),
    },
  });

  const onPick = (file: File | undefined) => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    importFile({ data: fd });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">1ª carga — importar planilha</CardTitle>
        <CardDescription>
          CSV ou XLSX com as colunas <code>sistema</code>, <code>periodicidade</code>
          (mensal/trimestral/semestral/anual) e <code>proxima_data</code> (AAAA-MM-DD ou
          DD/MM/AAAA). Faz upsert por sistema.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,.xlsx"
          className="hidden"
          onChange={(e) => onPick(e.target.files?.[0])}
        />
        <Button onClick={() => fileRef.current?.click()} disabled={isPending}>
          <Upload className="mr-2 h-4 w-4" />
          {isPending ? "Importando..." : "Selecionar planilha"}
        </Button>
      </CardContent>
    </Card>
  );
}

function ManualAddCard({
  systems,
  onDone,
}: {
  systems: SystemListOut[];
  onDone: () => void;
}) {
  const [systemId, setSystemId] = useState(systems[0]?.system_id || "");
  const [recurrence, setRecurrence] = useState<Recurrence>("QUARTERLY");
  const [date, setDate] = useState("");
  const { mutate: upsert, isPending } = useUpsertComplianceSchedule({
    mutation: {
      onSuccess: () => {
        onDone();
        toast.success("Agendamento salvo");
        setDate("");
      },
      onError: (e) => toast.error("Falha ao salvar", { description: String(e) }),
    },
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!systemId || !date) return;
    upsert({ data: { system_id: systemId, recurrence, next_due_date: date } });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Cadastrar / editar um sistema</CardTitle>
        <CardDescription>Define a periodicidade e a próxima data de avaliação.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-3">
          <select
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            value={systemId}
            onChange={(e) => setSystemId(e.target.value)}
            required
          >
            {systems.map((s) => (
              <option key={s.system_id} value={s.system_id}>
                {s.system_name}
              </option>
            ))}
          </select>
          <div className="grid grid-cols-2 gap-3">
            <select
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              value={recurrence}
              onChange={(e) => setRecurrence(e.target.value as Recurrence)}
            >
              {(Object.keys(RECURRENCE_LABEL) as Recurrence[]).map((r) => (
                <option key={r} value={r}>
                  {RECURRENCE_LABEL[r]}
                </option>
              ))}
            </select>
            <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
          </div>
          <Button type="submit" disabled={isPending || !systemId || !date}>
            {isPending ? "Salvando..." : "Salvar agendamento"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function SchedulesTable({
  schedules,
  onChanged,
}: {
  schedules: ComplianceScheduleOut[];
  onChanged: () => void;
}) {
  const { mutate: execute, isPending: executing } = useExecuteComplianceSchedule({
    mutation: {
      onSuccess: (s) => {
        onChanged();
        toast.success(`Execução registrada — próxima em ${s.next_due_date}`);
      },
      onError: (e) => toast.error("Falha ao registrar", { description: String(e) }),
    },
  });
  const { mutate: del } = useDeleteComplianceSchedule({
    mutation: {
      onSuccess: () => {
        onChanged();
        toast.success("Agendamento removido");
      },
      onError: (e) => toast.error("Falha ao remover", { description: String(e) }),
    },
  });

  if (schedules.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Nenhum agendamento cadastrado. Importe uma planilha ou cadastre um sistema acima.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Agendamentos</CardTitle>
        <CardDescription>{schedules.length} sistema(s) com calendário de conformidade.</CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="py-2 pr-3 font-medium">Sistema</th>
              <th className="py-2 pr-3 font-medium">Periodicidade</th>
              <th className="py-2 pr-3 font-medium">Próxima avaliação</th>
              <th className="py-2 pr-3 font-medium">Status</th>
              <th className="py-2 pr-3 font-medium">Última execução</th>
              <th className="py-2 pr-3 font-medium text-right">Ações</th>
            </tr>
          </thead>
          <tbody>
            {schedules.map((s) => (
              <tr key={s.calendar_id} className="border-b last:border-0">
                <td className="py-2 pr-3 font-medium">{s.system_name || s.system_id}</td>
                <td className="py-2 pr-3">{RECURRENCE_LABEL[s.recurrence]}</td>
                <td className="py-2 pr-3 font-mono">{s.next_due_date}</td>
                <td className="py-2 pr-3">
                  <DueBadge daysUntil={s.days_until} />
                </td>
                <td className="py-2 pr-3 text-muted-foreground">
                  {s.last_executed_at ? new Date(s.last_executed_at).toLocaleDateString("pt-BR") : "—"}
                </td>
                <td className="py-2 pr-3">
                  <div className="flex items-center justify-end gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={executing}
                      onClick={() => execute({ calendarId: s.calendar_id })}
                    >
                      <CheckCircle2 className="mr-1 h-4 w-4" />
                      Registrar execução
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        if (confirm(`Remover o calendário de "${s.system_name || s.system_id}"?`))
                          del({ calendarId: s.calendar_id });
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

/** Badge de status: vencida / vence hoje / vence em N dias / em dia.
 *  Derivado só de days_until (negativo = vencida, 0 = hoje). */
export function DueBadge({ daysUntil }: { daysUntil?: number | null }) {
  if (daysUntil == null) return <span className="text-muted-foreground">—</span>;
  if (daysUntil < 0) {
    return (
      <Badge variant="outline" className="border-destructive/40 text-destructive">
        Vencida há {Math.abs(daysUntil)}d
      </Badge>
    );
  }
  if (daysUntil === 0) {
    return (
      <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-300">
        <Clock className="mr-1 h-3 w-3" /> Vence hoje
      </Badge>
    );
  }
  if (daysUntil <= 30) {
    return (
      <Badge variant="outline" className="border-amber-500/40 text-amber-700 dark:text-amber-300">
        Em {daysUntil}d
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="border-emerald-500/40 text-emerald-700 dark:text-emerald-300">
      Em dia
    </Badge>
  );
}
