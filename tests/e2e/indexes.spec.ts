import { test, expect, type Route } from "@playwright/test";

/**
 * E2E da feature de índices + particionamento (F1-F7).
 *
 * Como o preview não tem backend rodando, interceptamos /api/* com
 * page.route() pra simular os cenários. Isso valida o plumbing do frontend
 * (cards renderizam, mutations disparam o request correto, badge editorial
 * aparece, warnings renderizam) sem depender de auth/SQL/Delta.
 */

const ENTITY_ID = "ent-test-1";
const SYSTEM_ID = "sys-test-1";

interface IndexFixture {
  index_id: string;
  index_name: string;
  index_type: string;
  columns: Array<{ name: string; direction: "ASC" | "DESC" }>;
  is_unique: boolean;
  include_columns: string[];
  partial_where: string | null;
  origin: "MANUAL" | "EXTRACTED" | null;
  pending_op?: "add" | "change" | "remove" | null;
  description_md: string | null;
  native_comment: string | null;
  created_at: string;
  created_by: string;
  updated_at: string;
  updated_by: string;
  entity_id: string;
}

function baseIndex(overrides: Partial<IndexFixture>): IndexFixture {
  return {
    index_id: "idx-1",
    entity_id: ENTITY_ID,
    index_name: "ix_default",
    index_type: "BTREE",
    columns: [{ name: "email", direction: "ASC" }],
    is_unique: false,
    include_columns: [],
    partial_where: null,
    origin: "MANUAL",
    pending_op: null,
    description_md: null,
    native_comment: null,
    created_at: new Date().toISOString(),
    created_by: "tester@x.com",
    updated_at: new Date().toISOString(),
    updated_by: "tester@x.com",
    ...overrides,
  };
}

async function stubApi(page: import("@playwright/test").Page, state: {
  indexes: IndexFixture[];
  warnings: Array<{ code: string; severity: string; message: string; related_index_ids: string[] }>;
}) {
  // Profile + RBAC — necessárias pro layout principal
  await page.route("**/api/profile", (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        email: "tester@x.com", name: "Tester",
        role: "ADMIN", roles: ["ADMIN"],
      }),
    }),
  );
  await page.route("**/api/rbac/me", (route: Route) =>
    route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ role: "ADMIN", roles: ["ADMIN"] }),
    }),
  );
  await page.route("**/api/features", (route: Route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "{}" }),
  );
  // Entity payload
  await page.route(`**/api/entities/${ENTITY_ID}`, (route: Route) =>
    route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({
        entity_id: ENTITY_ID, system_id: SYSTEM_ID,
        schema_name: "public", technical_name: "cliente",
        entity_type: "TABLE", tags: [], is_shared: false,
        attributes_count: 2,
        created_at: new Date().toISOString(), created_by: "tester@x.com",
        updated_at: new Date().toISOString(), updated_by: "tester@x.com",
      }),
    }),
  );
  // Systems list pra resolver technology
  await page.route("**/api/systems", (route: Route) =>
    route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify([
        {
          system_id: SYSTEM_ID, system_name: "Sistema Teste",
          technology: "PostgreSQL", is_active: true,
          created_at: new Date().toISOString(), created_by: "tester@x.com",
          updated_at: new Date().toISOString(), updated_by: "tester@x.com",
        },
      ]),
    }),
  );
  // Attributes
  await page.route(`**/api/entities/${ENTITY_ID}/attributes`, (route: Route) =>
    route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify([
        {
          attribute_id: "attr-1", entity_id: ENTITY_ID,
          technical_name: "id", is_primary_key: true,
          ordinal_position: 1, native_data_type: "BIGINT", is_nullable: false,
          created_at: new Date().toISOString(), created_by: "x",
          updated_at: new Date().toISOString(), updated_by: "x",
        },
        {
          attribute_id: "attr-2", entity_id: ENTITY_ID,
          technical_name: "email", is_primary_key: false,
          ordinal_position: 2, native_data_type: "VARCHAR(100)", is_nullable: true,
          created_at: new Date().toISOString(), created_by: "x",
          updated_at: new Date().toISOString(), updated_by: "x",
        },
      ]),
    }),
  );
  // Flags (não relevantes pra esse teste)
  await page.route(`**/api/entity-flags/${ENTITY_ID}`, (route: Route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  // Indexes — referencia o state corrente
  await page.route(`**/api/entities/${ENTITY_ID}/indexes`, (route: Route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify(state.indexes),
      });
    }
    if (route.request().method() === "POST") {
      const body = JSON.parse(route.request().postData() || "{}");
      const newIx = baseIndex({
        index_id: "idx-new", index_name: body.index_name,
        index_type: body.index_type, columns: body.columns,
        is_unique: !!body.is_unique, pending_op: "add",
      });
      state.indexes.push(newIx);
      return route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify(newIx),
      });
    }
    return route.fulfill({ status: 405 });
  });
  // Validate
  await page.route(`**/api/entities/${ENTITY_ID}/indexes/validate`, (route: Route) =>
    route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify(state.warnings),
    }),
  );
  // Partitioning
  await page.route(`**/api/entities/${ENTITY_ID}/partitioning`, (route: Route) =>
    route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({
        entity_id: ENTITY_ID, strategy: "NONE", columns: [],
      }),
    }),
  );
  // Tickets list (Cmd+K, top bar)
  await page.route("**/api/tickets**", (route: Route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
}

test.describe("Indexes UI (F1-F7)", () => {
  test("card de índices renderiza lista vazia", async ({ page }) => {
    const state = { indexes: [], warnings: [] };
    await stubApi(page, state);
    await page.goto(`/entities/${ENTITY_ID}`);
    await expect(page.getByText(/Índices/).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/Nenhum índice catalogado/)).toBeVisible();
    await expect(page.getByRole("button", { name: /Novo índice/i })).toBeVisible();
  });

  test("criar índice via UI mostra badge 'pending · add'", async ({ page }) => {
    const state = { indexes: [], warnings: [] };
    await stubApi(page, state);
    await page.goto(`/entities/${ENTITY_ID}`);

    await page.getByRole("button", { name: /Novo índice/i }).click();
    await page.getByPlaceholder(/Nome do índice/i).fill("ix_email");
    await page.getByRole("button", { name: /^Criar$/ }).click();

    await expect(page.getByText("ix_email")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(/pending · add/i)).toBeVisible();
  });

  test("warning PK_DUPLICATE aparece quando backend retorna", async ({ page }) => {
    const state = {
      indexes: [
        baseIndex({
          index_id: "idx-1",
          index_name: "ix_id",
          columns: [{ name: "id", direction: "ASC" }],
        }),
      ],
      warnings: [
        {
          code: "PK_DUPLICATE", severity: "warning",
          message: "Índice 'ix_id' duplica a PK (id).",
          related_index_ids: ["idx-1"],
        },
      ],
    };
    await stubApi(page, state);
    await page.goto(`/entities/${ENTITY_ID}`);
    await expect(page.getByText(/duplica a PK/i)).toBeVisible({ timeout: 10_000 });
  });
});
