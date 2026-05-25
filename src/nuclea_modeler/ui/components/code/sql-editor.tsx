import Editor from "@monaco-editor/react";

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
  return (
    <div className="rounded-md border overflow-hidden">
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
    </div>
  );
}
