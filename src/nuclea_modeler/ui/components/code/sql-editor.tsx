import { lazy, Suspense } from "react";
import { Skeleton } from "@/components/ui/skeleton";

// Monaco is ~1MB minified. Lazy-load it so the initial bundle stays small.
// The `vendor-monaco` manualChunk in vite.config.ts isolates Monaco's vendor
// code; lazy() ensures the chunk is only fetched when this component renders.
const Editor = lazy(() => import("@monaco-editor/react"));

interface SqlEditorProps {
  value: string;
  onChange: (v: string) => void;
  height?: number | string;
  language?: "sql" | "plaintext";
  readOnly?: boolean;
}

export function SqlEditor({
  value,
  onChange,
  height = 320,
  language = "sql",
  readOnly = false,
}: SqlEditorProps) {
  const heightStyle = typeof height === "number" ? `${height}px` : height;
  return (
    <div className="rounded-md border overflow-hidden">
      <Suspense
        fallback={
          <div
            className="flex items-center justify-center bg-muted/40"
            style={{ height: heightStyle }}
            aria-label="Carregando editor SQL"
          >
            <Skeleton className="w-3/4 h-6" />
          </div>
        }
      >
        <Editor
          height={height}
          language={language}
          value={value}
          onChange={(v) => onChange(v ?? "")}
          theme="vs-dark"
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            fontFamily:
              "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace",
            lineNumbers: "on",
            scrollBeyondLastLine: false,
            tabSize: 2,
            renderLineHighlight: "line",
            wordWrap: "on",
            readOnly,
            smoothScrolling: true,
            automaticLayout: true,
          }}
        />
      </Suspense>
    </div>
  );
}
