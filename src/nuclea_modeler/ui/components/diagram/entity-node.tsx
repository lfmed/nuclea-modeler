import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import { Key, ShieldAlert, Hash } from "lucide-react";
import type { DiagramEntity } from "@/lib/api";

interface EntityNodeData {
  entity: DiagramEntity;
  expanded: boolean;
  highlight?: boolean;
}

interface EntityNodeProps {
  data: EntityNodeData;
  selected?: boolean;
}

export const EntityNode = memo(({ data, selected }: EntityNodeProps) => {
  const { entity, expanded, highlight } = data;
  const showAttributes = expanded;

  return (
    <div
      className={`bg-card border rounded-lg shadow-sm min-w-[240px] max-w-[320px] transition-shadow ${
        selected
          ? "ring-2 ring-nuclea-primary shadow-lg"
          : highlight
            ? "ring-1 ring-nuclea-accent"
            : "border-border hover:shadow-md"
      }`}
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
            <h3 className="font-mono text-sm font-semibold truncate">
              {entity.technical_name}
            </h3>
            {entity.logical_name && (
              <p className="text-xs text-muted-foreground truncate">{entity.logical_name}</p>
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
        {entity.domain && (
          <span className="inline-block mt-1 text-[10px] bg-background border rounded px-1.5 py-0.5">
            {entity.domain}
          </span>
        )}
      </div>

      {/* Attributes */}
      {showAttributes && entity.attributes.length > 0 && (
        <ul className="divide-y text-xs">
          {entity.attributes.map((attr) => (
            <li
              key={attr.attribute_id}
              className="flex items-center gap-2 px-3 py-1.5 hover:bg-muted/30"
            >
              {attr.is_primary_key ? (
                <Key className="h-3 w-3 text-nuclea-primary shrink-0" />
              ) : (
                <span className="h-3 w-3 shrink-0" />
              )}
              <span className="font-mono flex-1 truncate">{attr.technical_name}</span>
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
            </li>
          ))}
        </ul>
      )}

      {!showAttributes && entity.attributes.length > 0 && (
        <div className="px-3 py-1.5 text-[10px] text-muted-foreground bg-muted/20 rounded-b-lg">
          {entity.attributes.length} atributo{entity.attributes.length !== 1 ? "s" : ""}
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
