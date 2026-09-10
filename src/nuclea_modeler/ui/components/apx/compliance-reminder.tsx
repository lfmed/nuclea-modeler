/**
 * Pop-up de lembrete de conformidade (rodada 8, item 3).
 *
 * Ao carregar o app, checa `/compliance/due` (avaliações vencidas/vencendo hoje) e,
 * se houver, exibe um modal pedindo a avaliação — com "Registrar execução" por
 * sistema (grava e avança a próxima data) e um link para o calendário. Dispensável
 * na sessão (sessionStorage), reaparece na próxima sessão enquanto houver pendência.
 *
 * Molde do WelcomeTour (pop-up automático). Usa query NÃO-suspense para não
 * bloquear o render do app; em erro/sem dados, renderiza null (degrada silencioso).
 */
import { useEffect, useRef, useState } from "react";
import { Link } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle, CalendarCheck, CheckCircle2 } from "lucide-react";

import { useComplianceDue, useExecuteComplianceSchedule, useMyRoles } from "@/lib/api";
import { Button } from "@/components/ui/button";

const DISMISS_KEY = "nuclea.complianceReminderDismissed";

function dismissedThisSession(): boolean {
  try {
    return sessionStorage.getItem(DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

export function ComplianceReminder() {
  const { data: due } = useComplianceDue(0);
  const { data: roles } = useMyRoles();
  const [dismissed, setDismissed] = useState(dismissedThisSession());
  const qc = useQueryClient();

  const { mutate: execute, isPending } = useExecuteComplianceSchedule({
    mutation: {
      onSuccess: (s) => {
        qc.invalidateQueries({ queryKey: ["complianceDue"] });
        qc.invalidateQueries({ queryKey: ["listComplianceSchedules"] });
        toast.success(`Execução registrada — próxima em ${s.next_due_date}`);
      },
      onError: (e) => toast.error("Falha ao registrar", { description: String(e) }),
    },
  });

  const dismiss = () => {
    try {
      sessionStorage.setItem(DISMISS_KEY, "1");
    } catch {
      /* ignore */
    }
    setDismissed(true);
  };

  const items = due || [];
  // Só quem PODE registrar a execução (curadoria) vê o pop-up — evita bloquear
  // usuários sem permissão com um modal cuja única ação retornaria 403 (achado
  // do /review). is_admin cobre ADMIN; os demais são DATA_ARCHITECT/DATA_STEWARD.
  const canAct =
    !!roles && (roles.is_admin || roles.roles.includes("DATA_ARCHITECT") || roles.roles.includes("DATA_STEWARD"));
  const visible = canAct && !dismissed && items.length > 0;

  // Escape fecha o modal (a11y) — SÓ enquanto ele está visível (senão um Esc em
  // qualquer tela dispensaria o lembrete da sessão antes de ele aparecer).
  useEffect(() => {
    if (!visible) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") dismiss();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  if (!visible) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={dismiss}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="compliance-reminder-title"
        className="w-full max-w-lg rounded-lg border bg-background p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-6 w-6 shrink-0 text-amber-500" />
          <div className="min-w-0 flex-1">
            <h2 id="compliance-reminder-title" className="text-lg font-semibold">
              Avaliação de conformidade pendente
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {items.length === 1
                ? "1 sistema está com a avaliação vencida ou vencendo hoje."
                : `${items.length} sistemas estão com a avaliação vencida ou vencendo hoje.`}{" "}
              Registre a execução quando concluir a avaliação (feita fora do app).
            </p>

            <div className="mt-3 max-h-64 space-y-2 overflow-y-auto">
              {items.map((s) => (
                <div
                  key={s.calendar_id}
                  className="flex items-center justify-between gap-3 rounded-md border p-2"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">
                      {s.system_name || s.system_id}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Prevista para <span className="font-mono">{s.next_due_date}</span>
                      {typeof s.days_until === "number" && s.days_until < 0
                        ? ` · vencida há ${Math.abs(s.days_until)}d`
                        : " · vence hoje"}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={isPending}
                    onClick={() => execute({ calendarId: s.calendar_id })}
                  >
                    <CheckCircle2 className="mr-1 h-4 w-4" />
                    Registrar execução
                  </Button>
                </div>
              ))}
            </div>

            <div className="mt-4 flex items-center justify-between gap-2">
              <Button variant="ghost" size="sm" asChild onClick={dismiss}>
                <Link to="/compliance">
                  <CalendarCheck className="mr-1 h-4 w-4" />
                  Ver calendário
                </Link>
              </Button>
              <Button variant="secondary" size="sm" onClick={dismiss}>
                Depois
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
