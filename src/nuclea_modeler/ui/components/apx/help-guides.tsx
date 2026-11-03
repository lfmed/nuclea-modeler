/**
 * Guias práticos da Central de Ajuda (rodada 9, item 10).
 *
 * Na avaliação, o cliente marcou "Canvas Exploratório" e "Linhagem" como "em
 * avaliação — necessário aprofundar o entendimento" e pediu "exemplos práticos de
 * utilização do recurso de Código DB". Este componente é o conteúdo dessa seção:
 * um passo a passo por recurso + exemplos COPIÁVEIS e um DDL de exemplo para
 * download (gerado no browser — sem backend, sem gravar nada no catálogo).
 *
 * Os campos citados batem com os formulários reais (code.*.new.tsx, lineage.tsx,
 * comparador.tsx). Se um formulário mudar, atualize o guia junto.
 */
import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Code2, Copy, Download, GitCompare, GitFork, Languages } from "lucide-react";

// ─── Exemplos de Código DB ──────────────────────────────────────────────────
// Um cenário único (cadastro de clientes) para os 4 tipos de objeto, em
// PostgreSQL — o dialeto do sistema do cliente nos testes. As views entram pelo
// import de DDL; procedures/triggers/sequences são cadastrados nos formulários do
// Código DB (o import de DDL hoje lê tabelas e views).

const SAMPLE_DDL = `-- Exemplo Núclea Modeler — Código DB (PostgreSQL)
-- 1) Importe este arquivo em Engenharia Reversa → Importar DDL (dialeto PostgreSQL).
--    As tabelas e a VIEW entram no modelo via ticket de aprovação.
-- 2) Depois, em Código DB → Views, abra "vw_cliente_ativo" e cole o SELECT abaixo
--    como definição; procedures/triggers/sequences são cadastrados nos formulários.

CREATE TABLE exemplo.cliente (
  id            BIGINT       NOT NULL,
  nome          VARCHAR(120) NOT NULL,
  documento     VARCHAR(14)  NOT NULL,
  status        CHAR(1)      NOT NULL DEFAULT 'A' CHECK (status IN ('A','I')),
  atualizado_em TIMESTAMP    NOT NULL,
  CONSTRAINT pk_cliente PRIMARY KEY (id)
);

CREATE TABLE exemplo.cliente_hist (
  id_hist    BIGINT      NOT NULL,
  cliente_id BIGINT      NOT NULL,
  status_ant CHAR(1),
  status_nov CHAR(1),
  alterado_em TIMESTAMP  NOT NULL,
  CONSTRAINT pk_cliente_hist PRIMARY KEY (id_hist),
  CONSTRAINT fk_hist_cliente FOREIGN KEY (cliente_id) REFERENCES exemplo.cliente (id)
);

CREATE VIEW exemplo.vw_cliente_ativo AS
SELECT id, nome, documento
FROM exemplo.cliente
WHERE status = 'A';
`;

interface CodeExample {
  kind: string;
  where: string;
  fields: { label: string; value: string }[];
  sql: string;
}

const CODE_EXAMPLES: CodeExample[] = [
  {
    kind: "View",
    where: "Entra pelo import de DDL; a definição SQL é colada em Código DB → Views → abrir a view.",
    fields: [
      { label: "Propósito", value: "Clientes ativos para consulta do atendimento" },
      { label: "Tabelas-base", value: "exemplo.cliente" },
    ],
    sql: `SELECT id, nome, documento
FROM exemplo.cliente
WHERE status = 'A';`,
  },
  {
    kind: "Procedure",
    where: "Código DB → Procedures → Nova procedure.",
    fields: [
      { label: "Schema / Nome técnico", value: "exemplo / prc_inativa_cliente" },
      { label: "Nome lógico", value: "Inativar cliente" },
      { label: "Comportamento", value: "Marca o cliente como inativo (status='I') e grava o histórico." },
      { label: "Risco de alteração", value: "ALTO — usada pelo fechamento diário" },
    ],
    sql: `CREATE OR REPLACE PROCEDURE exemplo.prc_inativa_cliente(p_id BIGINT)
LANGUAGE plpgsql AS $$
BEGIN
  UPDATE exemplo.cliente SET status = 'I', atualizado_em = now() WHERE id = p_id;
END;
$$;`,
  },
  {
    kind: "Trigger",
    where: "Código DB → Triggers → Novo trigger (associe à entidade exemplo.cliente).",
    fields: [
      { label: "Schema / Nome técnico", value: "exemplo / trg_cliente_hist" },
      { label: "Entidade associada", value: "exemplo.cliente" },
      { label: "Evento / Timing", value: "UPDATE / AFTER" },
      { label: "Comportamento", value: "Grava em cliente_hist toda mudança de status." },
    ],
    sql: `CREATE TRIGGER trg_cliente_hist
AFTER UPDATE OF status ON exemplo.cliente
FOR EACH ROW EXECUTE FUNCTION exemplo.fn_grava_hist();`,
  },
  {
    kind: "Sequence",
    where: "Código DB → Sequences → Nova sequence.",
    fields: [
      { label: "Schema / Nome técnico", value: "exemplo / seq_cliente_hist" },
      { label: "Valor inicial / Incremento", value: "1 / 1" },
      { label: "Cache", value: "20" },
    ],
    sql: `CREATE SEQUENCE exemplo.seq_cliente_hist START 1 INCREMENT 1 CACHE 20;`,
  },
];

function copy(text: string) {
  navigator.clipboard
    .writeText(text)
    .then(() => toast.success("Copiado"))
    .catch(() => toast.error("Não foi possível copiar — selecione o texto manualmente"));
}

function downloadSampleDdl() {
  const blob = new Blob([SAMPLE_DDL], { type: "text/sql;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "exemplo-codigo-db-postgres.sql";
  a.click();
  URL.revokeObjectURL(url);
}

function Steps({ items }: { items: React.ReactNode[] }) {
  return (
    <ol className="list-decimal space-y-1.5 pl-5 text-sm text-muted-foreground">
      {items.map((it, i) => (
        <li key={i}>{it}</li>
      ))}
    </ol>
  );
}

function CodeDbGuide() {
  const [open, setOpen] = useState<string | null>("View");
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Code2 className="h-4 w-4 text-nuclea-primary" /> Código DB — exemplos práticos
        </CardTitle>
        <CardDescription>
          Documenta o código que vive no banco (views, procedures, triggers, sequences): o que
          faz, qual tabela toca e o risco de alterar. Use o mesmo cenário abaixo para testar.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Steps
          items={[
            <>
              Baixe o DDL de exemplo e importe em{" "}
              <Link to="/extractions" className="underline">Engenharia Reversa → Importar DDL</Link>{" "}
              (dialeto PostgreSQL). Aprove o ticket.
            </>,
            <>
              Em <Link to="/code" className="underline">Código DB</Link> → Views, abra{" "}
              <code>vw_cliente_ativo</code> e cole a definição SQL.
            </>,
            <>Cadastre a procedure, o trigger e a sequence com os valores sugeridos abaixo.</>,
            <>
              Na lista de Triggers do Código DB, o <code>trg_cliente_hist</code> fica ligado à tabela{" "}
              <code>exemplo.cliente</code>, com o risco preenchido — é a consulta a fazer antes de
              alterar uma tabela que tem código dependente.
            </>,
          ]}
        />
        <Button variant="outline" size="sm" onClick={downloadSampleDdl}>
          <Download className="mr-2 h-4 w-4" /> Baixar DDL de exemplo (.sql)
        </Button>
        <div className="space-y-2">
          {CODE_EXAMPLES.map((ex) => (
            <details
              key={ex.kind}
              open={open === ex.kind}
              onToggle={(e) => (e.currentTarget as HTMLDetailsElement).open && setOpen(ex.kind)}
              className="rounded-md border"
            >
              <summary className="cursor-pointer px-3 py-2 text-sm font-medium">
                {ex.kind} <span className="font-normal text-muted-foreground">— {ex.where}</span>
              </summary>
              <div className="space-y-2 border-t px-3 py-3">
                <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-xs">
                  {ex.fields.map((f) => (
                    <div key={f.label} className="contents">
                      <dt className="text-muted-foreground">{f.label}</dt>
                      <dd>{f.value}</dd>
                    </div>
                  ))}
                </dl>
                <div className="relative">
                  <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">{ex.sql}</pre>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="absolute right-1 top-1 h-7 w-7"
                    onClick={() => copy(ex.sql)}
                    title="Copiar SQL"
                  >
                    <Copy className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            </details>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function CanvasGuide() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <GitCompare className="h-4 w-4 text-nuclea-primary" /> Canvas Exploratório — para que serve
        </CardTitle>
        <CardDescription>
          Um quadro livre para colocar tabelas lado a lado e comparar campos. Não altera o modelo:
          o quadro fica só no seu navegador.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="font-medium">Casos de uso</p>
        <Steps
          items={[
            <>
              <strong>Mesma tabela em duas versões:</strong> traga a tabela do modelo atual e a de
              uma versão publicada (Versões) para ver o que mudou coluna a coluna.
            </>,
            <>
              <strong>Tabelas parecidas em sistemas diferentes:</strong> ex. <code>cliente</code> do
              CRM × <code>pessoa</code> do cadastro — o canvas destaca campos em comum/diferentes
              (apoio a de-para e integração).
            </>,
            <>
              <strong>Print para reunião/e-mail:</strong> exporte o quadro ou um cartão em PNG.
            </>,
          ]}
        />
        <p>
          Abra em <Link to="/comparador" className="underline">Canvas Exploratório</Link>, adicione
          os cartões pelo seletor de objeto e arraste para organizar.
        </p>
      </CardContent>
    </Card>
  );
}

function LineageGuide() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <GitFork className="h-4 w-4 text-nuclea-primary" /> Linhagem — de onde vem, para onde vai
        </CardTitle>
        <CardDescription>
          Registra, por tabela, quem a ALIMENTA (upstream) e quem a CONSOME (downstream) — base
          para análise de impacto antes de mudar uma estrutura.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="font-medium">Exemplo prático (tabela exemplo.cliente)</p>
        <Steps
          items={[
            <>
              Em <Link to="/lineage" className="underline">Linhagem</Link>, escolha a tabela.
            </>,
            <>
              <strong>Upstream:</strong> sistema de origem <code>CRM</code>, objeto{" "}
              <code>crm.tb_cliente</code>, integração <code>CDC</code>, periodicidade{" "}
              <code>REAL_TIME</code>, transformações "normaliza documento" e o link do pipeline.
            </>,
            <>
              <strong>Downstream:</strong> consumidor <code>Data Lake Risco</code>, tipo{" "}
              <code>DIRECT_READ</code>, time responsável e SLA <code>HIGH</code>.
            </>,
            <>
              O grafo mostra origem → tabela → consumidores. Antes de alterar a tabela, confira os
              consumidores com SLA alto e avise os times responsáveis.
            </>,
          ]}
        />
      </CardContent>
    </Card>
  );
}

function DialectGuide() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Languages className="h-4 w-4 text-nuclea-primary" /> Onde definir o dialeto
        </CardTitle>
        <CardDescription>
          O dialeto (banco) é uma propriedade do SISTEMA.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <Steps
          items={[
            <>
              Defina ao criar o sistema (campo <strong>Tecnologia (dialeto)</strong>) ou depois, no{" "}
              <Link to="/explorer" className="underline">Navegador</Link>: clique no selo ao lado do
              nome do sistema (ou em <strong>+ dialeto</strong>).
            </>,
            <>
              Ele define os tipos, índices e estratégias de particionamento oferecidos ao editar
              tabelas, e vem pré-selecionado no <strong>Importar DDL</strong>.
            </>,
            <>
              No <strong>Exportar DDL</strong> o dialeto é livre (o destino costuma ser outro banco,
              ex. Databricks); há um atalho “usar o dialeto do sistema”.
            </>,
            <>
              <strong>DynamoDB (não relacional):</strong> escolha a tecnologia “DynamoDB”. O modelo
              entra por <Link to="/extractions" className="underline">Engenharia Reversa</Link> → aba{" "}
              <strong>DynamoDB (JSON)</strong> (saída do <code>aws dynamodb describe-table</code>,
              NoSQL Workbench ou CloudFormation) e sai em <strong>Exportar DDL → DynamoDB (JSON)</strong>{" "}
              (input do <code>create-table</code>). Partition + sort key = PK; GSI/LSI = índices.
            </>,
          ]}
        />
      </CardContent>
    </Card>
  );
}

export function PracticalGuides() {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="lg:col-span-2">
        <CodeDbGuide />
      </div>
      <CanvasGuide />
      <LineageGuide />
      <DialectGuide />
    </div>
  );
}
