import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import { ShieldAlert, Hash, Zap, GitBranch } from "lucide-react";
import type { DiagramEntity } from "@/lib/api";
import { PkBadge, computePkOrdinals } from "@/components/attributes/pk-controls";

interface EntityNodeData {
  entity: DiagramEntity;
  expanded: boolean;
  highlight?: boolean;
}

interface EntityNodeProps {
  data: EntityNodeData;
  selected?: boolean;
}

/**
 * Visual feedback for entities with pending edits in the user's editorial
 * session. Borders override the normal selected/highlight ring styling so the
 * pending state is immediately recognizable on the canvas.
 */
const pendingBorderClass = (op?: string | null) => {
  if (op === "add") return "border-2 border-dashed border-emerald-500";
  if (op === "change") return "border-2 border-amber-500";
  if (op === "remove") return "border-2 border-rose-500/60";
  return "";
};

const pendingBadgeClass = (op?: string | null) => {
  if (op === "add") return "bg-emerald-500/15 text-emerald-700 border-emerald-500/40";
  if (op === "change") return "bg-amber-500/15 text-amber-700 border-amber-500/40";
  if (op === "remove") return "bg-rose-500/15 text-rose-700 border-rose-500/40";
  return "bg-muted text-muted-foreground border-border";
};

const pendingLabel = (op?: string | null) => {
  if (op === "add") return "adicionar";
  if (op === "change") return "alterar";
  if (op === "remove") return "remover";
  return op || "";
};

export const EntityNode = memo(({ data, selected }: EntityNodeProps) => {
  const { entity, expanded, highlight } = data;
  const showAttributes = expanded;
  const pendingOp = entity.pending_op ?? null;
  const hasPending = !!pendingOp;
  const isRemove = pendingOp === "remove";
  // PK composta numerada (PK1, PK2…) na ordem de definição — legível de relance.
  const pkOrdinals = computePkOrdinals(entity.attributes);

  return (
    <div
      className={`bg-card rounded-lg shadow-sm min-w-[240px] max-w-[320px] transition-shadow ${
        hasPending
          ? pendingBorderClass(pendingOp)
          : selected
            ? "border ring-2 ring-nuclea-primary shadow-lg"
            : highlight
              ? "border ring-1 ring-nuclea-accent"
              : "border border-border hover:shadow-md"
      } ${isRemove ? "opacity-50" : ""}`}
    >
      {/* Header */}
      <div
        className={`px-3 py-2 rounded-t-lg border-b ${
          entity.has_lgpd_flag
            ? "bg-nuclea-primary/10 border-nuclea-primary/30"
            : "bg-muted/50"
        }`}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground mb-0.5">
              <Hash className="h-3 w-3" />
              {entity.schema_name}
              <span className="px-1 py-0.5 rounded text-[9px] font-semibold bg-background border">
                {entity.entity_type}
              </span>
            </div>
            <h3
              className={`font-mono text-sm font-semibold truncate ${
                isRemove ? "line-through" : ""
              }`}
            >
              {entity.technical_name}
            </h3>
            {entity.logical_name && (
              <p
                className={`text-xs text-muted-foreground truncate ${
                  isRemove ? "line-through" : ""
                }`}
              >
                {entity.logical_name}
              </p>
            )}
          </div>
          {entity.has_lgpd_flag && (
            <div
              className="shrink-0 rounded-full bg-nuclea-primary text-primary-foreground p-1"
              title="Contém dados LGPD"
            >
              <ShieldAlert className="h-3 w-3" />
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-1 mt-1">
          {entity.domain && (
            <span className="text-[10px] bg-background border rounded px-1.5 py-0.5">
              {entity.domain}
            </span>
          )}
          {(entity.indexes_count ?? 0) > 0 && (
            <span
              className="text-[10px] rounded px-1.5 py-0.5 border bg-sky-500/10 border-sky-500/30 font-mono"
              title={`${entity.indexes_count} índice(s) catalogado(s)`}
            >
              {entity.indexes_count} idx
            </span>
          )}
          {entity.partition_strategy && entity.partition_strategy !== "NONE" && (
            <span
              className="text-[10px] rounded px-1.5 py-0.5 border bg-violet-500/10 border-violet-500/30 font-mono"
              title={`Particionamento: ${entity.partition_strategy}`}
            >
              {entity.partition_strategy}
            </span>
          )}
          {hasPending && (
            <span
              className={`text-[10px] rounded px-1.5 py-0.5 border font-medium ${pendingBadgeClass(pendingOp)}`}
              title="Mudança pendente nesta sessão"
            >
              pendente · {pendingLabel(pendingOp)}
            </span>
          )}
        </div>
      </div>

      {/* Attributes */}
      {showAttributes && entity.attributes.length > 0 && (
        <ul className="divide-y text-xs">
          {entity.attributes.map((attr) => {
            const attrPending = attr.pending_op ?? null;
            const attrRemove = attrPending === "remove";
            return (
              <li
                key={attr.attribute_id}
                className={`flex items-center gap-2 px-3 py-1.5 hover:bg-muted/30 ${
                  attrPending === "add"
                    ? "bg-emerald-500/5"
                    : attrPending === "change"
                      ? "bg-amber-500/5"
                      : attrRemove
                        ? "bg-rose-500/5 opacity-70"
                        : ""
                }`}
              >
                {attr.is_primary_key ? (
                  <PkBadge ordinal={pkOrdinals.get(attr.attribute_id)} />
                ) : attr.is_indexed ? (
                  // Tooltip nativo (P2): o wrapper <span title> carrega o tooltip
                  // porque o ícone lucide não aceita `title`. Explica o ícone no
                  // canvas, onde não há TooltipProvider do Radix ao redor do ReactFlow.
                  <span
                    className="shrink-0"
                    title="Coluna indexada (faz parte de um índice)"
                  >
                    <Zap className="h-3 w-3 text-sky-500" aria-label="Está em índice" />
                  </span>
                ) : (
                  <span className="h-3 w-3 shrink-0" />
                )}
                <span
                  className={`font-mono flex-1 truncate ${
                    attrRemove ? "line-through" : ""
                  }`}
                >
                  {attr.technical_name}
                </span>
                {attr.has_lgpd_flag && (
                  <ShieldAlert
                    className="h-3 w-3 text-nuclea-primary shrink-0"
                    aria-label="LGPD"
                  />
                )}
                {attr.native_data_type && (
                  <span className="text-[10px] text-muted-foreground font-mono shrink-0">
                    {attr.native_data_type}
                  </span>
                )}
                {attr.is_nullable === false && (
                  <span
                    className="text-[10px] text-amber-600 dark:text-amber-400 shrink-0"
                    title="NOT NULL"
                  >
                    *
                  </span>
                )}
                {attrPending && (
                  <span
                    className={`text-[9px] rounded px-1 py-0.5 border shrink-0 ${pendingBadgeClass(attrPending)}`}
                    title="Mudança pendente"
                  >
                    {pendingLabel(attrPending)}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {showAttributes && (entity.indexes?.length || entity.partition_strategy && entity.partition_strategy !== "NONE") && (
        <div className="border-t bg-muted/10 px-3 py-1.5 space-y-1">
          {(entity.indexes ?? []).slice(0, 5).map((ix) => (
            <div
              key={ix.index_name}
              className="flex items-center gap-1.5 text-[10px] font-mono"
              title={`${ix.index_type}${ix.is_unique ? " UNIQUE" : ""}`}
            >
              <Zap className="h-2.5 w-2.5 text-sky-500 shrink-0" />
              <span className="text-muted-foreground truncate">
                <span className="text-foreground">{ix.index_name}</span>
                {" · "}
                {ix.columns.join(", ") || "(sem colunas)"}
              </span>
            </div>
          ))}
          {(entity.indexes?.length ?? 0) > 5 && (
            <div className="text-[10px] text-muted-foreground italic">
              + {(entity.indexes!.length - 5)} índice(s) — veja na entity
            </div>
          )}
          {entity.partition_strategy && entity.partition_strategy !== "NONE" && (
            <div
              className="flex items-center gap-1.5 text-[10px] font-mono"
              title={`Particionamento ${entity.partition_strategy}`}
            >
              <GitBranch className="h-2.5 w-2.5 text-violet-500 shrink-0" />
              <span className="text-muted-foreground truncate">
                <span className="text-foreground">{entity.partition_strategy}</span>
                {(entity.partition_columns?.length ?? 0) > 0 && (
                  <>
                    {" · "}
                    {entity.partition_columns!.join(", ")}
                  </>
                )}
              </span>
            </div>
          )}
        </div>
      )}

      {!showAttributes && entity.attributes.length > 0 && (
        <div className="px-3 py-1.5 text-[10px] text-muted-foreground bg-muted/20 rounded-b-lg">
          {entity.attributes.length} atributo{entity.attributes.length !== 1 ? "s" : ""}
          {(entity.indexes_count ?? 0) > 0 && (
            <span className="ml-2">· {entity.indexes_count} idx</span>
          )}
        </div>
      )}

      <Handle
        type="target"
        position={Position.Left}
        className="!bg-nuclea-primary !w-2 !h-2 !border-2 !border-background"
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!bg-nuclea-primary !w-2 !h-2 !border-2 !border-background"
      />
    </div>
  );
});
EntityNode.displayName = "EntityNode";
