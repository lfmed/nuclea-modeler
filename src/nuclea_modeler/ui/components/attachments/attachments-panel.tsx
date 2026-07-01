import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Paperclip, Upload, Download, Trash2 } from "lucide-react";

import {
  useListAttachments,
  useUploadAttachment,
  useDeleteAttachment,
  downloadAttachment,
  type AttachmentOwnerKind,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const MAX_MB = 25;

function humanSize(bytes?: number | null): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AttachmentsPanel({
  ownerKind,
  ownerId,
  label = "Anexos",
  description = "Documentos anexados (PDF, imagens, planilhas…). Máx. 25 MB por arquivo.",
}: {
  ownerKind: AttachmentOwnerKind;
  ownerId: string;
  label?: string;
  description?: string;
}) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [note, setNote] = useState("");

  const { data: items = [], isLoading } = useListAttachments(ownerKind, ownerId);

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["listAttachments", ownerKind, ownerId] });

  const upload = useUploadAttachment({
    mutation: {
      onSuccess: () => {
        toast.success("Arquivo anexado");
        setNote("");
        if (fileRef.current) fileRef.current.value = "";
        invalidate();
      },
      onError: (e) => toast.error("Falha ao anexar", { description: e.message }),
    },
  });

  const remove = useDeleteAttachment({
    mutation: {
      onSuccess: () => {
        toast.success("Anexo removido");
        invalidate();
      },
      onError: (e) => toast.error("Falha ao remover", { description: e.message }),
    },
  });

  function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > MAX_MB * 1024 * 1024) {
      toast.error(`Arquivo muito grande (máx. ${MAX_MB} MB)`);
      if (fileRef.current) fileRef.current.value = "";
      return;
    }
    const fd = new FormData();
    fd.append("file", f);
    fd.append("owner_kind", ownerKind);
    fd.append("owner_id", ownerId);
    if (note.trim()) fd.append("description", note.trim());
    upload.mutate({ data: fd });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Paperclip className="h-5 w-5" />
          {label} ({items.length})
        </CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Nota (opcional) para o próximo anexo"
            className="max-w-xs"
            disabled={upload.isPending}
          />
          <input
            ref={fileRef}
            type="file"
            className="hidden"
            onChange={onPick}
            disabled={upload.isPending}
          />
          <Button
            size="sm"
            variant="outline"
            onClick={() => fileRef.current?.click()}
            disabled={upload.isPending}
          >
            <Upload className="mr-2 h-4 w-4" />
            {upload.isPending ? "Enviando..." : "Anexar arquivo"}
          </Button>
        </div>

        {isLoading ? (
          <p className="text-sm text-muted-foreground">Carregando anexos…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground italic">Nenhum anexo ainda.</p>
        ) : (
          <ul className="divide-y rounded-md border">
            {items.map((a) => (
              <li
                key={a.attachment_id}
                className="flex items-center justify-between gap-2 px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{a.original_filename}</p>
                  <p className="text-xs text-muted-foreground">
                    {humanSize(a.file_size_bytes)} · {a.created_by} ·{" "}
                    {new Date(a.created_at).toLocaleString("pt-BR")}
                    {a.description ? ` · ${a.description}` : ""}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    title="Baixar"
                    onClick={() =>
                      downloadAttachment(a.attachment_id, a.original_filename).catch(
                        (e) => toast.error("Falha ao baixar", { description: String(e) }),
                      )
                    }
                  >
                    <Download className="h-4 w-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    title="Remover"
                    disabled={remove.isPending}
                    onClick={() => {
                      if (confirm(`Remover o anexo "${a.original_filename}"?`))
                        remove.mutate({ attachmentId: a.attachment_id });
                    }}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
