/**
 * Hand-written API client for the Núclea Modeler UI.
 *
 * Replaces the auto-generated lib/api.ts that apx normally produces from the
 * FastAPI OpenAPI schema. Kept intentionally small and explicit since we
 * deploy without apx and don't have the codegen step.
 *
 * Signature mirrors what apx/orval emits: `use<Op>` (mutation),
 * `use<Op>Suspense` (query), with a `selector()` helper that maps Axios's
 * `{ data }` envelope to the bare payload.
 */
import {
  useSuspenseQuery,
  useQuery,
  useMutation,
  type UseSuspenseQueryOptions,
  type UseMutationOptions,
} from "@tanstack/react-query";
import axios, { type AxiosResponse } from "axios";

const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

// Interceptor de erro: o FastAPI devolve `{ "detail": "..." }` nos erros
// (HTTPException). Por padrão o axios só expõe "Request failed with status code
// NNN" em `error.message`, escondendo a mensagem útil. Aqui promovemos o `detail`
// para `error.message`, para que os toasts / ErrorBoundary mostrem a orientação
// real ao usuário (ex.: "peça ao admin: GRANT CREATE VOLUME ...").
api.interceptors.response.use(
  (r) => r,
  (error) => {
    const detail = error?.response?.data?.detail;
    if (detail) {
      error.message = typeof detail === "string" ? detail : JSON.stringify(detail);
    }
    return Promise.reject(error);
  },
);

type Selector<T> = {
  query?: Pick<
    UseSuspenseQueryOptions<AxiosResponse<T>, Error, T>,
    "select" | "staleTime"
  >;
};

// ─── Types ────────────────────────────────────────────────────────────────────

export type Environment = "HINT" | "HEXT" | "PROD";
export type ConnectionType = "ODBC" | "REST" | "DDL_IMPORT";
export type TestStatus = "success" | "failure" | "never";

export type SystemEnvironment = "DEV" | "HINT" | "PRD";

export interface SystemListOut {
  system_id: string;
  system_name: string;
  domain?: string | null;
  technology?: string | null;
  environment?: SystemEnvironment | null;
  is_active: boolean;
}

export interface SystemOut extends SystemListOut {
  description?: string | null;
  owner_team?: string | null;
  created_at: string;
  created_by: string;
  updated_at: string;
  updated_by: string;
}

export interface SystemIn {
  system_name: string;
  description?: string | null;
  domain?: string | null;
  owner_team?: string | null;
  technology?: string | null;
  environment?: SystemEnvironment | null;
  is_active?: boolean;
}

export interface ConnectionListOut {
  connection_id: string;
  alias: string;
  environment: Environment;
  system_id: string;
  system_name?: string | null;
  connection_type: ConnectionType;
  last_test_status?: TestStatus | null;
  last_test_at?: string | null;
  last_test_latency_ms?: number | null;
  updated_at: string;
}

export interface ConnectionOut extends ConnectionListOut {
  config: Record<string, unknown>;
  secret_scope?: string | null;
  secret_key_user?: string | null;
  secret_key_pass?: string | null;
  secret_key_token?: string | null;
  last_test_db_version?: string | null;
  last_test_error?: string | null;
  created_at: string;
  created_by: string;
  updated_by: string;
}

export interface ConnectionIn {
  alias: string;
  environment: Environment;
  system_id: string;
  connection_type: ConnectionType;
  config: Record<string, unknown>;
  secret_scope?: string | null;
  secret_key_user?: string | null;
  secret_key_pass?: string | null;
  secret_key_token?: string | null;
}

export interface ConnectionTestResult {
  status: TestStatus;
  latency_ms?: number | null;
  db_version?: string | null;
  error?: string | null;
  tested_at: string;
}

export type EntityType = "TABLE" | "VIEW" | "MATERIALIZED_VIEW" | "EXTERNAL";
export type Criticality = "HIGH" | "MEDIUM" | "LOW";

export interface EntityListOut {
  entity_id: string;
  system_id: string;
  system_name?: string | null;
  schema_name: string;
  technical_name: string;
  logical_name?: string | null;
  entity_type: EntityType;
  domain?: string | null;
  criticality?: Criticality | null;
  attributes_count?: number | null;
  updated_at: string;
  // Editorial session — quando há mudança pendente no ticket de sessão
  pending_op?: "add" | "change" | "remove" | null;
  pending_ticket_id?: string | null;
}

export interface EntityOut extends EntityListOut {
  description_md?: string | null;
  business_owner?: string | null;
  technical_owner?: string | null;
  tags: string[];
  notes?: string | null;
  native_comment?: string | null;
  row_count_approx?: number | null;
  last_extracted_at?: string | null;
  created_at: string;
  created_by: string;
  updated_by: string;
}

export interface EntityIn {
  system_id: string;
  schema_name: string;
  technical_name: string;
  logical_name?: string | null;
  description_md?: string | null;
  domain?: string | null;
  business_owner?: string | null;
  technical_owner?: string | null;
  criticality?: Criticality | null;
  tags?: string[];
  notes?: string | null;
  entity_type?: EntityType;
  native_comment?: string | null;
  row_count_approx?: number | null;
  is_shared?: boolean;
}

export interface AttributeOut {
  attribute_id: string;
  entity_id: string;
  technical_name: string;
  logical_name?: string | null;
  ordinal_position?: number | null;
  native_data_type?: string | null;
  is_nullable?: boolean | null;
  default_value?: string | null;
  is_primary_key: boolean;
  description_md?: string | null;
  business_rule?: string | null;
  sample_value?: string | null;
  glossary_term_id?: string | null;
  native_comment?: string | null;
  created_at: string;
  created_by: string;
  updated_at: string;
  updated_by: string;
}

export interface AttributeIn {
  entity_id: string;
  technical_name: string;
  logical_name?: string | null;
  ordinal_position?: number | null;
  native_data_type?: string | null;
  is_nullable?: boolean | null;
  default_value?: string | null;
  is_primary_key?: boolean;
  description_md?: string | null;
  business_rule?: string | null;
  sample_value?: string | null;
  glossary_term_id?: string | null;
  native_comment?: string | null;
}

export interface CurrentUser {
  id?: string;
  user_name?: string;
  display_name?: string;
  active?: boolean | null;
  external_id?: string;
  name?: { given_name?: string; family_name?: string };
  emails?: { value: string; primary?: boolean; type?: string }[];
  groups?: { value: string; display?: string }[];
  roles?: { value: string }[];
  entitlements?: { value: string }[];
}

// ─── Suspense queries ─────────────────────────────────────────────────────────

export const useCurrentUserSuspense = (s?: Selector<CurrentUser>) =>
  useSuspenseQuery({
    queryKey: ["currentUser"],
    queryFn: () => api.get<CurrentUser>("/current-user"),
    select: (r) => r.data,
    ...s?.query,
  });

// ─── Feature flags ──────────────────────────────────────────────────────────

export interface FeaturesOut {
  features: Record<string, boolean>;
}

export const useGetFeaturesSuspense = (s?: Selector<FeaturesOut>) =>
  useSuspenseQuery({
    queryKey: ["features"],
    queryFn: () => api.get<FeaturesOut>("/features"),
    select: (r) => r.data,
    // Feature flags resetam apenas no redeploy — cache infinito local é OK.
    staleTime: Infinity,
    ...s?.query,
  });

export const useListSystemsSuspense = (s?: Selector<SystemListOut[]>) =>
  useSuspenseQuery({
    queryKey: ["listSystems"],
    queryFn: () => api.get<SystemListOut[]>("/systems"),
    select: (r) => r.data,
    ...s?.query,
  });

export const useCreateSystem = (
  opts?: Opts<SystemOut, { data: SystemIn }>,
) =>
  useMutation({
    mutationFn: async ({ data }) =>
      (await api.post<SystemOut>("/systems", data)).data,
    ...opts?.mutation,
  });

export const useListConnectionsSuspense = (s?: Selector<ConnectionListOut[]>) =>
  useSuspenseQuery({
    queryKey: ["listConnections"],
    queryFn: () => api.get<ConnectionListOut[]>("/connections"),
    select: (r) => r.data,
    ...s?.query,
  });

export const useGetConnectionSuspense = (id: string, s?: Selector<ConnectionOut>) =>
  useSuspenseQuery({
    queryKey: ["getConnection", id],
    queryFn: () => api.get<ConnectionOut>(`/connections/${encodeURIComponent(id)}`),
    select: (r) => r.data,
    ...s?.query,
  });

// Non-suspense variant for routes that need to render even without data
export const useGetConnection = (id: string | undefined) =>
  useQuery({
    queryKey: ["getConnection", id],
    queryFn: () => api.get<ConnectionOut>(`/connections/${encodeURIComponent(id!)}`).then((r) => r.data),
    enabled: !!id,
  });

export const useListEntitiesSuspense = (
  params: { systemId?: string; domain?: string } = {},
  s?: Selector<EntityListOut[]>,
) =>
  useSuspenseQuery({
    queryKey: ["listEntities", params],
    queryFn: () =>
      api.get<EntityListOut[]>("/entities", {
        params: {
          system_id: params.systemId,
          domain: params.domain,
        },
      }),
    select: (r) => r.data,
    ...s?.query,
  });

export const useGetEntitySuspense = (id: string, s?: Selector<EntityOut>) =>
  useSuspenseQuery({
    queryKey: ["getEntity", id],
    queryFn: () => api.get<EntityOut>(`/entities/${encodeURIComponent(id)}`),
    select: (r) => r.data,
    ...s?.query,
  });

export const useListAttributesSuspense = (entityId: string, s?: Selector<AttributeOut[]>) =>
  useSuspenseQuery({
    queryKey: ["listAttributes", entityId],
    queryFn: () =>
      api.get<AttributeOut[]>(`/entities/${encodeURIComponent(entityId)}/attributes`),
    select: (r) => r.data,
    ...s?.query,
  });

// Variante não-suspense — usada no Comparador, onde cada cartão carrega os
// atributos da sua entidade independentemente (N cartões, fetch condicional).
export const useEntityAttributes = (entityId: string | null | undefined) =>
  useQuery({
    queryKey: ["listAttributes", entityId],
    queryFn: () =>
      api
        .get<AttributeOut[]>(`/entities/${encodeURIComponent(entityId!)}/attributes`)
        .then((r) => r.data),
    enabled: !!entityId,
  });

// ─── Mutations ────────────────────────────────────────────────────────────────

type Opts<TData, TVars> = {
  mutation?: Omit<UseMutationOptions<TData, Error, TVars>, "mutationFn">;
};

export const useCreateConnection = (opts?: Opts<ConnectionOut, { data: ConnectionIn }>) =>
  useMutation({
    mutationFn: async ({ data }) => (await api.post<ConnectionOut>("/connections", data)).data,
    ...opts?.mutation,
  });

export const useUpdateConnection = (
  opts?: Opts<ConnectionOut, { connectionId: string; data: ConnectionIn }>,
) =>
  useMutation({
    mutationFn: async ({ connectionId, data }) =>
      (await api.put<ConnectionOut>(`/connections/${encodeURIComponent(connectionId)}`, data)).data,
    ...opts?.mutation,
  });

export const useDeleteConnection = (
  opts?: Opts<{ deleted: string }, { connectionId: string }>,
) =>
  useMutation({
    mutationFn: async ({ connectionId }) =>
      (await api.delete<{ deleted: string }>(`/connections/${encodeURIComponent(connectionId)}`)).data,
    ...opts?.mutation,
  });

export const useTestConnection = (
  opts?: Opts<ConnectionTestResult, { connectionId: string }>,
) =>
  useMutation({
    mutationFn: async ({ connectionId }) =>
      (await api.post<ConnectionTestResult>(`/connections/${encodeURIComponent(connectionId)}/test`)).data,
    ...opts?.mutation,
  });

export const useCreateEntity = (opts?: Opts<EntityOut, { data: EntityIn }>) =>
  useMutation({
    mutationFn: async ({ data }) => (await api.post<EntityOut>("/entities", data)).data,
    ...opts?.mutation,
  });

export const useUpdateEntity = (
  opts?: Opts<EntityOut, { entityId: string; data: EntityIn }>,
) =>
  useMutation({
    mutationFn: async ({ entityId, data }) =>
      (await api.put<EntityOut>(`/entities/${encodeURIComponent(entityId)}`, data)).data,
    ...opts?.mutation,
  });

export const useDeleteEntity = (opts?: Opts<{ deleted: string }, { entityId: string }>) =>
  useMutation({
    mutationFn: async ({ entityId }) =>
      (await api.delete<{ deleted: string }>(`/entities/${encodeURIComponent(entityId)}`)).data,
    ...opts?.mutation,
  });

export const useCreateAttribute = (
  opts?: Opts<AttributeOut, { entityId: string; data: AttributeIn }>,
) =>
  useMutation({
    mutationFn: async ({ entityId, data }) =>
      (await api.post<AttributeOut>(
        `/entities/${encodeURIComponent(entityId)}/attributes`,
        data,
      )).data,
    ...opts?.mutation,
  });

export const useUpdateAttribute = (
  opts?: Opts<
    AttributeOut,
    { entityId: string; attributeId: string; data: AttributeIn }
  >,
) =>
  useMutation({
    mutationFn: async ({ entityId, attributeId, data }) =>
      (await api.put<AttributeOut>(
        `/entities/${encodeURIComponent(entityId)}/attributes/${encodeURIComponent(attributeId)}`,
        data,
      )).data,
    ...opts?.mutation,
  });

export const useDeleteAttribute = (
  opts?: Opts<{ deleted: string }, { entityId: string; attributeId: string }>,
) =>
  useMutation({
    mutationFn: async ({ entityId, attributeId }) =>
      (await api.delete<{ deleted: string }>(
        `/entities/${encodeURIComponent(entityId)}/attributes/${encodeURIComponent(attributeId)}`,
      )).data,
    ...opts?.mutation,
  });

// ─── Indexes & Partitioning ──────────────────────────────────────────────────

export type IndexType =
  | "BTREE" | "HASH" | "UNIQUE" | "GIN" | "BRIN" | "GIST"
  | "BITMAP" | "CLUSTERED" | "NONCLUSTERED"
  | "Z-ORDER" | "LIQUID";

export type ColumnDirection = "ASC" | "DESC";
export type PartitionStrategy = "RANGE" | "LIST" | "HASH" | "LIQUID" | "NONE";

export interface IndexColumn {
  name: string;
  direction: ColumnDirection;
}

export interface EntityIndexIn {
  entity_id: string;
  index_name: string;
  index_type: IndexType;
  columns: IndexColumn[];
  include_columns?: string[];
  partial_where?: string | null;
  is_unique?: boolean;
  description_md?: string | null;
  native_comment?: string | null;
}

export interface EntityIndexOut {
  index_id: string;
  entity_id: string;
  index_name: string;
  index_type: IndexType;
  columns: IndexColumn[];
  include_columns: string[];
  partial_where: string | null;
  is_unique: boolean;
  description_md: string | null;
  native_comment: string | null;
  origin: "EXTRACTED" | "MANUAL" | null;
  created_at: string;
  created_by: string;
  updated_at: string;
  updated_by: string;
  pending_op?: "add" | "change" | "remove" | null;
}

export interface EntityPartitioningIn {
  entity_id: string;
  strategy: PartitionStrategy;
  columns: string[];
  num_partitions?: number | null;
  bounds?: Record<string, unknown[]> | null;
  description_md?: string | null;
}

export interface EntityPartitioningOut {
  entity_id: string;
  strategy: PartitionStrategy;
  columns: string[];
  num_partitions: number | null;
  bounds: Record<string, unknown[]> | null;
  description_md: string | null;
  origin: "EXTRACTED" | "MANUAL" | null;
  created_at?: string | null;
  created_by?: string | null;
  updated_at?: string | null;
  updated_by?: string | null;
  pending_op?: "add" | "change" | "remove" | null;
}

export const useListEntityIndexesSuspense = (
  entityId: string,
  s?: Selector<EntityIndexOut[]>,
) =>
  useSuspenseQuery({
    queryKey: ["listEntityIndexes", entityId],
    queryFn: async () =>
      (await api.get<EntityIndexOut[]>(
        `/entities/${encodeURIComponent(entityId)}/indexes`,
      )).data,
    ...s,
  });

export const useCreateEntityIndex = (
  opts?: Opts<EntityIndexOut, { entityId: string; data: EntityIndexIn }>,
) =>
  useMutation({
    mutationFn: async ({ entityId, data }) =>
      (await api.post<EntityIndexOut>(
        `/entities/${encodeURIComponent(entityId)}/indexes`,
        data,
      )).data,
    ...opts?.mutation,
  });

export const useUpdateEntityIndex = (
  opts?: Opts<
    EntityIndexOut,
    { entityId: string; indexId: string; data: EntityIndexIn }
  >,
) =>
  useMutation({
    mutationFn: async ({ entityId, indexId, data }) =>
      (await api.put<EntityIndexOut>(
        `/entities/${encodeURIComponent(entityId)}/indexes/${encodeURIComponent(indexId)}`,
        data,
      )).data,
    ...opts?.mutation,
  });

export const useDeleteEntityIndex = (
  opts?: Opts<
    { deleted: string; pending?: boolean; ticket_id?: string },
    { entityId: string; indexId: string }
  >,
) =>
  useMutation({
    mutationFn: async ({ entityId, indexId }) =>
      (await api.delete<{ deleted: string; pending?: boolean; ticket_id?: string }>(
        `/entities/${encodeURIComponent(entityId)}/indexes/${encodeURIComponent(indexId)}`,
      )).data,
    ...opts?.mutation,
  });

export interface IndexValidationWarning {
  code:
    | "PK_DUPLICATE"
    | "PK_LEADING"
    | "INDEX_SUBSET"
    | "PARTITION_NULLABLE"
    | "PARTITION_UNKNOWN_COLUMN";
  severity: "info" | "warning";
  message: string;
  related_index_ids: string[];
}

export const useValidateEntityIndexesSuspense = (
  entityId: string,
  s?: Selector<IndexValidationWarning[]>,
) =>
  useSuspenseQuery({
    queryKey: ["validateEntityIndexes", entityId],
    queryFn: async () =>
      (await api.get<IndexValidationWarning[]>(
        `/entities/${encodeURIComponent(entityId)}/indexes/validate`,
      )).data,
    ...s,
  });

export const useGetEntityPartitioningSuspense = (
  entityId: string,
  s?: Selector<EntityPartitioningOut>,
) =>
  useSuspenseQuery({
    queryKey: ["getEntityPartitioning", entityId],
    queryFn: async () =>
      (await api.get<EntityPartitioningOut>(
        `/entities/${encodeURIComponent(entityId)}/partitioning`,
      )).data,
    ...s,
  });

export const useSetEntityPartitioning = (
  opts?: Opts<
    EntityPartitioningOut,
    { entityId: string; data: EntityPartitioningIn }
  >,
) =>
  useMutation({
    mutationFn: async ({ entityId, data }) =>
      (await api.put<EntityPartitioningOut>(
        `/entities/${encodeURIComponent(entityId)}/partitioning`,
        data,
      )).data,
    ...opts?.mutation,
  });

// ─── RBAC ─────────────────────────────────────────────────────────────────────

export type RoleName =
  | "DATA_ARCHITECT"
  | "DATA_STEWARD"
  | "DATA_ENGINEER"
  | "CDE"
  | "ADMIN";

export interface MyRolesOut {
  user_email: string;
  roles: RoleName[];
  can_approve_tickets: boolean;
  can_apply_tickets: boolean;
  can_create_connections: boolean;
  is_admin: boolean;
}

export interface UserRoleOut {
  user_role_id: string;
  user_email: string;
  role_name: RoleName;
  granted_at: string;
  granted_by: string;
  is_active: boolean;
}

export interface UserRoleIn {
  user_email: string;
  role_name: RoleName;
}

export const useMyRolesSuspense = (s?: Selector<MyRolesOut>) =>
  useSuspenseQuery({
    queryKey: ["myRoles"],
    queryFn: () => api.get<MyRolesOut>("/rbac/me"),
    select: (r) => r.data,
    ...s?.query,
  });

export const useListRolesSuspense = (s?: Selector<UserRoleOut[]>) =>
  useSuspenseQuery({
    queryKey: ["listRoles"],
    queryFn: () => api.get<UserRoleOut[]>("/rbac"),
    select: (r) => r.data,
    ...s?.query,
  });

export const useGrantRole = (opts?: Opts<UserRoleOut, { data: UserRoleIn }>) =>
  useMutation({
    mutationFn: async ({ data }) => (await api.post<UserRoleOut>("/rbac", data)).data,
    ...opts?.mutation,
  });

export const useRevokeRole = (opts?: Opts<{ revoked: string }, { userRoleId: string }>) =>
  useMutation({
    mutationFn: async ({ userRoleId }) =>
      (await api.delete<{ revoked: string }>(`/rbac/${encodeURIComponent(userRoleId)}`)).data,
    ...opts?.mutation,
  });

// ─── Tickets ─────────────────────────────────────────────────────────────────

export type TicketStatus = "OPEN" | "APPROVED" | "APPLIED" | "REJECTED";
export type TicketSource = "REVERSE_ENG" | "DDL_IMPORT" | "LAKEBASE_ROUNDTRIP" | "MANUAL";

export interface DiffEntity {
  op: "add" | "remove" | "change";
  schema_name: string;
  technical_name: string;
  entity_type?: string;
  payload?: Record<string, unknown> | null;
  field_changes?: Array<Record<string, unknown>> | null;
  attributes?: Array<Record<string, unknown>> | null;
}

export interface TicketDiff {
  entities: DiffEntity[];
  additions: number;
  removals: number;
  changes: number;
}

export interface TicketListOut {
  ticket_id: string;
  title: string;
  system_id: string;
  system_name?: string | null;
  source_type: TicketSource;
  status: TicketStatus;
  additions_count: number;
  removals_count: number;
  changes_count: number;
  created_at: string;
  created_by: string;
  approved_at?: string | null;
  approved_by?: string | null;
  applied_at?: string | null;
}

export interface TicketOut extends TicketListOut {
  extraction_id?: string | null;
  summary_md?: string | null;
  diff: TicketDiff;
  applied_by?: string | null;
  rejected_at?: string | null;
  rejected_by?: string | null;
  rejection_reason?: string | null;
  target_version_id?: string | null;
}

export interface TicketApplyResult {
  ticket_id: string;
  status: TicketStatus;
  applied_entities: number;
  applied_attributes: number;
  reversed_items?: number;
  ignored_items?: number;
  errors: string[];
}

export type DecisionAction = "apply" | "ignore" | "reverse";

export interface FieldDecision {
  field: string;
  action: DecisionAction;
}

export interface EntityDecision {
  schema_name: string;
  technical_name: string;
  op: "add" | "remove" | "change";
  action: DecisionAction;
  field_decisions: FieldDecision[];
}

export interface TicketApplyIn {
  decisions?: EntityDecision[] | null;
  reverse_sandbox_id?: string | null;
}

export const useListTicketsSuspense = (
  params: { status?: TicketStatus; systemId?: string } = {},
  s?: Selector<TicketListOut[]>,
) =>
  useSuspenseQuery({
    queryKey: ["listTickets", params],
    queryFn: () =>
      api.get<TicketListOut[]>("/tickets", {
        params: { status: params.status, system_id: params.systemId },
      }),
    select: (r) => r.data,
    ...s?.query,
  });

export const useGetTicketSuspense = (id: string, s?: Selector<TicketOut>) =>
  useSuspenseQuery({
    queryKey: ["getTicket", id],
    queryFn: () => api.get<TicketOut>(`/tickets/${encodeURIComponent(id)}`),
    select: (r) => r.data,
    ...s?.query,
  });

export const useApproveTicket = (
  opts?: Opts<TicketOut, { ticketId: string; note?: string }>,
) =>
  useMutation({
    mutationFn: async ({ ticketId, note }) =>
      (await api.post<TicketOut>(`/tickets/${encodeURIComponent(ticketId)}/approve`, { note })).data,
    ...opts?.mutation,
  });

export const useRejectTicket = (
  opts?: Opts<TicketOut, { ticketId: string; reason: string }>,
) =>
  useMutation({
    mutationFn: async ({ ticketId, reason }) =>
      (await api.post<TicketOut>(`/tickets/${encodeURIComponent(ticketId)}/reject`, { reason })).data,
    ...opts?.mutation,
  });

export const useReopenTicket = (
  opts?: Opts<TicketApplyResult, { ticketId: string }>,
) =>
  useMutation({
    mutationFn: async ({ ticketId }) =>
      (await api.post<TicketApplyResult>(`/tickets/${encodeURIComponent(ticketId)}/reopen`)).data,
    ...opts?.mutation,
  });

export const useApplyTicket = (
  opts?: Opts<TicketApplyResult, { ticketId: string; data?: TicketApplyIn }>,
) =>
  useMutation({
    mutationFn: async ({ ticketId, data }) =>
      (
        await api.post<TicketApplyResult>(
          `/tickets/${encodeURIComponent(ticketId)}/apply`,
          data ?? {},
        )
      ).data,
    ...opts?.mutation,
  });

// NOTA: hooks abaixo adicionados à mão (espelhando o padrão do orval) porque o
// codegen (refresh_openapi) não roda no ambiente atual. Rodar refresh_openapi
// numa máquina com pypi liberado canoniza estas definições.

export const useApproveAndApplyTicket = (
  opts?: Opts<TicketApplyResult, { ticketId: string; note?: string }>,
) =>
  useMutation({
    mutationFn: async ({ ticketId, note }) =>
      (
        await api.post<TicketApplyResult>(
          `/tickets/${encodeURIComponent(ticketId)}/approve-apply`,
          { note },
        )
      ).data,
    ...opts?.mutation,
  });

export type BatchAction = "approve" | "reject" | "apply" | "approve_and_apply";

export interface BatchTicketIn {
  ticket_ids: string[];
  action: BatchAction;
  note?: string | null;
  reason?: string | null;
}

export interface BatchTicketItemResult {
  ticket_id: string;
  ok: boolean;
  status?: TicketStatus | null;
  applied_entities: number;
  applied_attributes: number;
  error?: string | null;
}

export interface BatchTicketResult {
  action: BatchAction;
  total: number;
  succeeded: number;
  failed: number;
  results: BatchTicketItemResult[];
}

export const useBatchTicketAction = (
  opts?: Opts<BatchTicketResult, { data: BatchTicketIn }>,
) =>
  useMutation({
    mutationFn: async ({ data }) =>
      (await api.post<BatchTicketResult>("/tickets/batch", data)).data,
    ...opts?.mutation,
  });

// ─── Sync (Módulo 9) ──────────────────────────────────────────────────────────

export type SyncMode = "INCREMENTAL" | "FULL";
export type SyncStatus = "RUNNING" | "SUCCESS" | "PARTIAL" | "FAILED";
export type SyncObjectStatus = "OK" | "SKIPPED" | "ERROR";

export interface SyncRunRequest {
  system_id: string;
  target_catalog: string;
  target_schema_map?: Record<string, string> | null;
  target_schema?: string | null;
  mode?: SyncMode;
  dry_run?: boolean;
  materialize?: boolean;
}

export interface SyncObjectResult {
  schema_name: string;
  technical_name: string;
  target_table: string;
  status: SyncObjectStatus;
  message?: string | null;
  ddl?: string | null;
}

export interface SyncRunResult {
  sync_id: string;
  status: SyncStatus;
  objects_total: number;
  objects_synced: number;
  objects_failed: number;
  objects_created: number;
  duration_ms: number;
  target_catalog: string;
  dry_run: boolean;
  materialize: boolean;
  errors: string[];
  objects: SyncObjectResult[];
}

export interface SyncLogListOut {
  sync_id: string;
  system_id: string;
  started_at: string;
  ended_at?: string | null;
  status: SyncStatus;
  objects_total?: number | null;
  objects_synced?: number | null;
  objects_failed?: number | null;
  duration_ms?: number | null;
  target_catalog?: string | null;
  triggered_by?: string | null;
  error_summary?: string | null;
}

export interface SyncLogOut extends SyncLogListOut {
  version_id: string;
  objects: SyncObjectResult[];
}

export const useListSyncRunsSuspense = (s?: Selector<SyncLogListOut[]>) =>
  useSuspenseQuery({
    queryKey: ["listSyncRuns"],
    queryFn: () => api.get<SyncLogListOut[]>("/sync/runs"),
    select: (r) => r.data,
    ...s?.query,
  });

export const useGetSyncRunSuspense = (id: string, s?: Selector<SyncLogOut>) =>
  useSuspenseQuery({
    queryKey: ["getSyncRun", id],
    queryFn: () => api.get<SyncLogOut>(`/sync/runs/${encodeURIComponent(id)}`),
    select: (r) => r.data,
    ...s?.query,
  });

export const useRunSync = (opts?: Opts<SyncRunResult, { data: SyncRunRequest }>) =>
  useMutation({
    mutationFn: async ({ data }) =>
      (await api.post<SyncRunResult>("/sync/run", data)).data,
    ...opts?.mutation,
  });

export const usePreviewSync = (opts?: Opts<SyncRunResult, { data: SyncRunRequest }>) =>
  useMutation({
    mutationFn: async ({ data }) =>
      (await api.post<SyncRunResult>("/sync/preview", data)).data,
    ...opts?.mutation,
  });

// ─── Anexos (documentos em entidades/modelos) ─────────────────────────────────

export type AttachmentOwnerKind = "entity" | "schema" | "diagram" | "system";

export interface AttachmentListOut {
  attachment_id: string;
  owner_kind: AttachmentOwnerKind;
  owner_id: string;
  original_filename: string;
  mime_type?: string | null;
  file_size_bytes?: number | null;
  description?: string | null;
  created_at: string;
  created_by: string;
}

export type AttachmentOut = AttachmentListOut;

export const useListAttachments = (
  ownerKind: string | null | undefined,
  ownerId: string | null | undefined,
) =>
  useQuery({
    queryKey: ["listAttachments", ownerKind, ownerId],
    queryFn: () =>
      api
        .get<AttachmentListOut[]>("/attachments", {
          params: { owner_kind: ownerKind, owner_id: ownerId },
        })
        .then((r) => r.data),
    enabled: !!ownerKind && !!ownerId,
  });

// Upload via multipart. Content-Type é deixado undefined de propósito para o
// axios/browser definirem o boundary a partir do FormData.
export const useUploadAttachment = (opts?: Opts<AttachmentOut, { data: FormData }>) =>
  useMutation({
    mutationFn: async ({ data }) =>
      (
        await api.post<AttachmentOut>("/attachments", data, {
          headers: { "Content-Type": undefined },
        } as never)
      ).data,
    ...opts?.mutation,
  });

export const useDeleteAttachment = (
  opts?: Opts<{ ok: boolean }, { attachmentId: string }>,
) =>
  useMutation({
    mutationFn: async ({ attachmentId }) =>
      (
        await api.delete<{ ok: boolean }>(
          `/attachments/${encodeURIComponent(attachmentId)}`,
        )
      ).data,
    ...opts?.mutation,
  });

// Baixa os bytes e dispara o download no browser.
export async function downloadAttachment(
  attachmentId: string,
  filename: string,
): Promise<void> {
  const resp = await api.get(
    `/attachments/${encodeURIComponent(attachmentId)}/download`,
    { responseType: "blob" },
  );
  const url = URL.createObjectURL(resp.data as Blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

// ─── Flags (Módulo 5) ────────────────────────────────────────────────────────

export type FlagCategory = "LGPD" | "USE" | "QUALITY" | "CUSTOM";

export interface FlagOut {
  flag_id: string;
  flag_key: string;
  category: FlagCategory;
  display_name: string;
  description?: string | null;
  color_hex?: string | null;
  requires_justification: boolean;
  is_system: boolean;
  is_active: boolean;
  uc_tag_key?: string | null;
}

export interface FlagIn {
  flag_key: string;
  category?: FlagCategory;
  display_name: string;
  description?: string | null;
  color_hex?: string | null;
  requires_justification?: boolean;
}

export interface FlagPatch {
  is_active?: boolean | null;
  display_name?: string | null;
  description?: string | null;
  color_hex?: string | null;
  requires_justification?: boolean | null;
}

export interface EntityFlagApplyIn {
  flag_id: string;
  justification?: string | null;
}

export interface EntityFlagOut {
  entity_flag_id: string;
  entity_id: string;
  flag_id: string;
  flag: FlagOut;
  justification?: string | null;
  applied_at: string;
  applied_by: string;
  applied_in_version?: string | null;
  is_propagated: boolean;
}

export interface AttributeFlagApplyIn {
  flag_id: string;
  justification?: string | null;
}

export interface AttributeFlagOut {
  attribute_flag_id: string;
  attribute_id: string;
  flag_id: string;
  flag: FlagOut;
  justification?: string | null;
  applied_at: string;
  applied_by: string;
  applied_in_version?: string | null;
}

export const useListFlagsSuspense = (
  params: { category?: FlagCategory; isActive?: boolean } = {},
  s?: Selector<FlagOut[]>,
) =>
  useSuspenseQuery({
    queryKey: ["listFlags", params],
    queryFn: () =>
      api.get<FlagOut[]>("/flags", {
        params: {
          category: params.category,
          is_active: params.isActive,
        },
      }),
    select: (r) => r.data,
    ...s?.query,
  });

export const useCreateCustomFlag = (opts?: Opts<FlagOut, { data: FlagIn }>) =>
  useMutation({
    mutationFn: async ({ data }) => (await api.post<FlagOut>("/flags", data)).data,
    ...opts?.mutation,
  });

export const useToggleFlag = (
  opts?: Opts<FlagOut, { flagId: string; data: FlagPatch }>,
) =>
  useMutation({
    mutationFn: async ({ flagId, data }) =>
      (await api.patch<FlagOut>(`/flags/${encodeURIComponent(flagId)}`, data)).data,
    ...opts?.mutation,
  });

export const useListEntityFlagsSuspense = (
  entityId: string,
  s?: Selector<EntityFlagOut[]>,
) =>
  useSuspenseQuery({
    queryKey: ["listEntityFlags", entityId],
    queryFn: () =>
      api.get<EntityFlagOut[]>(
        `/entities/${encodeURIComponent(entityId)}/flags`,
      ),
    select: (r) => r.data,
    ...s?.query,
  });

export const useApplyEntityFlag = (
  opts?: Opts<EntityFlagOut, { entityId: string; data: EntityFlagApplyIn }>,
) =>
  useMutation({
    mutationFn: async ({ entityId, data }) =>
      (await api.post<EntityFlagOut>(
        `/entities/${encodeURIComponent(entityId)}/flags`,
        data,
      )).data,
    ...opts?.mutation,
  });

export const useRemoveEntityFlag = (
  opts?: Opts<
    { deleted: string },
    { entityId: string; entityFlagId: string }
  >,
) =>
  useMutation({
    mutationFn: async ({ entityId, entityFlagId }) =>
      (await api.delete<{ deleted: string }>(
        `/entities/${encodeURIComponent(entityId)}/flags/${encodeURIComponent(entityFlagId)}`,
      )).data,
    ...opts?.mutation,
  });

export const useListAttributeFlagsSuspense = (
  attributeId: string,
  s?: Selector<AttributeFlagOut[]>,
) =>
  useSuspenseQuery({
    queryKey: ["listAttributeFlags", attributeId],
    queryFn: () =>
      api.get<AttributeFlagOut[]>(
        `/attributes/${encodeURIComponent(attributeId)}/flags`,
      ),
    select: (r) => r.data,
    ...s?.query,
  });

export const useApplyAttributeFlag = (
  opts?: Opts<
    AttributeFlagOut,
    { attributeId: string; data: AttributeFlagApplyIn }
  >,
) =>
  useMutation({
    mutationFn: async ({ attributeId, data }) =>
      (await api.post<AttributeFlagOut>(
        `/attributes/${encodeURIComponent(attributeId)}/flags`,
        data,
      )).data,
    ...opts?.mutation,
  });

export const useRemoveAttributeFlag = (
  opts?: Opts<
    { deleted: string },
    { attributeId: string; attributeFlagId: string }
  >,
) =>
  useMutation({
    mutationFn: async ({ attributeId, attributeFlagId }) =>
      (await api.delete<{ deleted: string }>(
        `/attributes/${encodeURIComponent(attributeId)}/flags/${encodeURIComponent(attributeFlagId)}`,
      )).data,
    ...opts?.mutation,
  });

// ─── DDL Export (Módulo 10) ──────────────────────────────────────────────────

export type DDLDialect =
  | "ANSI"
  | "TSQL"
  | "PLSQL"
  | "POSTGRES"
  | "MYSQL"
  | "SPARKSQL";

export interface DDLDialectInfo {
  code: DDLDialect;
  label: string;
  subtitle: string;
}

export interface DDLExportRequest {
  system_id: string;
  dialect: DDLDialect;
  include_comments?: boolean;
  qualify_schema?: boolean;
  include_drop_if_exists?: boolean;
  one_file_per_object?: boolean;
  entity_ids?: string[] | null;
}

export interface DDLObjectResult {
  object_name: string;
  object_kind: "TABLE" | "VIEW";
  ddl_text: string;
  errors: string[];
}

export interface DDLExportResult {
  dialect: DDLDialect;
  total_objects: number;
  success_count: number;
  error_count: number;
  files: DDLObjectResult[];
  combined_text: string;
}

export const useListDdlDialectsSuspense = (s?: Selector<DDLDialectInfo[]>) =>
  useSuspenseQuery({
    queryKey: ["listDdlDialects"],
    queryFn: () => api.get<DDLDialectInfo[]>("/ddl/dialects"),
    select: (r) => r.data,
    ...s?.query,
  });

export const useExportDdl = (
  opts?: Opts<DDLExportResult, { data: DDLExportRequest }>,
) =>
  useMutation({
    mutationFn: async ({ data }) =>
      (await api.post<DDLExportResult>("/ddl/export", data)).data,
    ...opts?.mutation,
  });

export const usePreviewDdl = (
  opts?: Opts<DDLExportResult, { data: DDLExportRequest }>,
) =>
  useMutation({
    mutationFn: async ({ data }) =>
      (await api.post<DDLExportResult>("/ddl/preview", data)).data,
    ...opts?.mutation,
  });

// ─── Glossary (Module 6) ─────────────────────────────────────────────────────

export type TermStatus = "DRAFT" | "IN_REVIEW" | "APPROVED" | "DEPRECATED";
export type ConceptualType =
  | "IDENTIFIER"
  | "MONETARY"
  | "DATE"
  | "BOOLEAN"
  | "TEXT"
  | "NUMERIC"
  | "CATEGORICAL"
  | "OTHER";

export interface TermIn {
  canonical_name: string;
  definition: string;
  synonyms?: string[];
  domain?: string | null;
  conceptual_type?: ConceptualType | null;
  valid_examples?: string[];
  owner_person?: string | null;
}

export interface TermListOut {
  term_id: string;
  canonical_name: string;
  domain?: string | null;
  conceptual_type?: ConceptualType | null;
  status: TermStatus;
  owner_person?: string | null;
  mappings_count: number;
  updated_at: string;
}

export interface TermOut {
  term_id: string;
  canonical_name: string;
  definition: string;
  synonyms: string[];
  domain?: string | null;
  conceptual_type?: ConceptualType | null;
  valid_examples: string[];
  owner_person?: string | null;
  status: TermStatus;
  approved_by?: string | null;
  approved_at?: string | null;
  created_at: string;
  created_by: string;
  updated_at: string;
  updated_by: string;
  mappings_count: number;
}

export interface MappingIn {
  term_id: string;
  attribute_id: string;
  inherit_description?: boolean;
  override_description?: string | null;
}

export interface MappingOut {
  mapping_id: string;
  term_id: string;
  attribute_id: string;
  inherit_description: boolean;
  override_description?: string | null;
  type_compat_warning: boolean;
  created_at: string;
  created_by: string;
  term_canonical_name?: string | null;
  term_status?: TermStatus | null;
  term_conceptual_type?: ConceptualType | null;
  term_definition?: string | null;
  attribute_technical_name?: string | null;
  attribute_logical_name?: string | null;
  native_data_type?: string | null;
  entity_id?: string | null;
  entity_technical_name?: string | null;
  schema_name?: string | null;
  system_id?: string | null;
  system_name?: string | null;
}

export const useListTermsSuspense = (
  params: { status?: TermStatus; domain?: string; q?: string } = {},
  s?: Selector<TermListOut[]>,
) =>
  useSuspenseQuery({
    queryKey: ["listTerms", params],
    queryFn: () =>
      api.get<TermListOut[]>("/glossary/terms", {
        params: {
          status: params.status,
          domain: params.domain,
          q: params.q,
        },
      }),
    select: (r) => r.data,
    ...s?.query,
  });

export const useGetTermSuspense = (id: string, s?: Selector<TermOut>) =>
  useSuspenseQuery({
    queryKey: ["getTerm", id],
    queryFn: () => api.get<TermOut>(`/glossary/terms/${encodeURIComponent(id)}`),
    select: (r) => r.data,
    ...s?.query,
  });

export const useListTermMappingsSuspense = (
  termId: string,
  s?: Selector<MappingOut[]>,
) =>
  useSuspenseQuery({
    queryKey: ["listTermMappings", termId],
    queryFn: () =>
      api.get<MappingOut[]>(`/glossary/terms/${encodeURIComponent(termId)}/mappings`),
    select: (r) => r.data,
    ...s?.query,
  });

export const useListAttributeGlossarySuspense = (
  attributeId: string,
  s?: Selector<MappingOut[]>,
) =>
  useSuspenseQuery({
    queryKey: ["listAttributeGlossary", attributeId],
    queryFn: () =>
      api.get<MappingOut[]>(
        `/attributes/${encodeURIComponent(attributeId)}/glossary`,
      ),
    select: (r) => r.data,
    ...s?.query,
  });

export const useCreateTerm = (opts?: Opts<TermOut, { data: TermIn }>) =>
  useMutation({
    mutationFn: async ({ data }) =>
      (await api.post<TermOut>("/glossary/terms", data)).data,
    ...opts?.mutation,
  });

export const useUpdateTerm = (
  opts?: Opts<TermOut, { termId: string; data: TermIn }>,
) =>
  useMutation({
    mutationFn: async ({ termId, data }) =>
      (await api.put<TermOut>(`/glossary/terms/${encodeURIComponent(termId)}`, data)).data,
    ...opts?.mutation,
  });

export const useTransitionTerm = (
  opts?: Opts<TermOut, { termId: string; to: TermStatus; note?: string }>,
) =>
  useMutation({
    mutationFn: async ({ termId, to, note }) =>
      (
        await api.post<TermOut>(
          `/glossary/terms/${encodeURIComponent(termId)}/transitions`,
          { to, note },
        )
      ).data,
    ...opts?.mutation,
  });

export const useDeleteTerm = (
  opts?: Opts<{ deprecated: string }, { termId: string }>,
) =>
  useMutation({
    mutationFn: async ({ termId }) =>
      (
        await api.delete<{ deprecated: string }>(
          `/glossary/terms/${encodeURIComponent(termId)}`,
        )
      ).data,
    ...opts?.mutation,
  });

export const useCreateMapping = (
  opts?: Opts<MappingOut, { termId: string; data: MappingIn }>,
) =>
  useMutation({
    mutationFn: async ({ termId, data }) =>
      (
        await api.post<MappingOut>(
          `/glossary/terms/${encodeURIComponent(termId)}/mappings`,
          data,
        )
      ).data,
    ...opts?.mutation,
  });

export const useDeleteMapping = (
  opts?: Opts<{ deleted: string }, { mappingId: string }>,
) =>
  useMutation({
    mutationFn: async ({ mappingId }) =>
      (
        await api.delete<{ deleted: string }>(
          `/glossary/mappings/${encodeURIComponent(mappingId)}`,
        )
      ).data,
    ...opts?.mutation,
  });

// ─── Versions (Módulo 8) ─────────────────────────────────────────────────────

export type VersionStatus = "DRAFT" | "PUBLISHED" | "ACTIVE" | "DEPRECATED";

export type DiffEntryType =
  | "entity_added"
  | "entity_removed"
  | "entity_changed"
  | "attribute_added"
  | "attribute_removed"
  | "attribute_changed";

export interface VersionListOut {
  version_id: string;
  system_id: string;
  system_name?: string | null;
  version_number: string;
  title?: string | null;
  status: VersionStatus;
  published_at?: string | null;
  published_by?: string | null;
  created_at: string;
  created_by: string;
}

export interface VersionOut extends VersionListOut {
  changelog?: string | null;
  based_on_version?: string | null;
  snapshot_json: Record<string, unknown>;
  updated_at: string;
  updated_by: string;
}

export interface PublishRequest {
  system_id: string;
  title: string;
  changelog?: string;
  make_active?: boolean;
}

export interface DiffEntry {
  type: DiffEntryType;
  entity_key: string;
  attribute_key?: string | null;
  field?: string | null;
  before?: unknown;
  after?: unknown;
}

export interface VersionDiff {
  from_version_id: string;
  to_version_id: string;
  additions: DiffEntry[];
  removals: DiffEntry[];
  changes: DiffEntry[];
  totals: { additions: number; removals: number; changes: number };
}

export const useListVersionsSuspense = (
  systemId?: string,
  s?: Selector<VersionListOut[]>,
) =>
  useSuspenseQuery({
    queryKey: ["listVersions", systemId ?? null],
    queryFn: () =>
      api.get<VersionListOut[]>("/versions", {
        params: { system_id: systemId },
      }),
    select: (r) => r.data,
    ...s?.query,
  });

export const useGetVersionSuspense = (id: string, s?: Selector<VersionOut>) =>
  useSuspenseQuery({
    queryKey: ["getVersion", id],
    queryFn: () => api.get<VersionOut>(`/versions/${encodeURIComponent(id)}`),
    select: (r) => r.data,
    ...s?.query,
  });

// Variante não-suspense — Comparador carrega o snapshot de uma versão para
// extrair os campos de uma entidade naquela versão (fetch condicional por cartão).
export const useVersion = (id: string | null | undefined) =>
  useQuery({
    queryKey: ["getVersion", id],
    queryFn: () =>
      api.get<VersionOut>(`/versions/${encodeURIComponent(id!)}`).then((r) => r.data),
    enabled: !!id,
  });

export const useVersionDiffSuspense = (
  params: { from: string; to: string },
  s?: Selector<VersionDiff>,
) =>
  useSuspenseQuery({
    queryKey: ["versionDiff", params.from, params.to],
    queryFn: () =>
      api.get<VersionDiff>("/versions/diff", {
        params: { from: params.from, to: params.to },
      }),
    select: (r) => r.data,
    ...s?.query,
  });

export const usePublishVersion = (
  opts?: Opts<VersionOut, { data: PublishRequest }>,
) =>
  useMutation({
    mutationFn: async ({ data }) =>
      (await api.post<VersionOut>("/versions/publish", data)).data,
    ...opts?.mutation,
  });

export const useRestoreVersion = (
  opts?: Opts<VersionOut, { versionId: string }>,
) =>
  useMutation({
    mutationFn: async ({ versionId }) =>
      (await api.post<VersionOut>(
        `/versions/${encodeURIComponent(versionId)}/restore`,
      )).data,
    ...opts?.mutation,
  });

export const useDeprecateVersion = (
  opts?: Opts<VersionOut, { versionId: string }>,
) =>
  useMutation({
    mutationFn: async ({ versionId }) =>
      (await api.post<VersionOut>(
        `/versions/${encodeURIComponent(versionId)}/deprecate`,
      )).data,
    ...opts?.mutation,
  });

// ─── Lakebase Sandboxes ───────────────────────────────────────────────────────

export interface SandboxListOut {
  sandbox_id: string;
  name: string;
  instance_name: string;
  database_name: string;
  default_schema: string;
  pg_version?: string | null;
  last_test_status?: string | null;
  last_test_at?: string | null;
  is_active: boolean;
}

export interface SandboxOut extends SandboxListOut {
  instance_uid?: string | null;
  read_write_dns?: string | null;
  description?: string | null;
  last_test_error?: string | null;
  created_at: string;
  created_by: string;
  updated_at: string;
  updated_by: string;
}

export interface SandboxIn {
  name: string;
  instance_name: string;
  database_name?: string;
  default_schema?: string;
  description?: string | null;
}

export interface SandboxTestResult {
  status: "success" | "failure";
  server_version?: string | null;
  current_db?: string | null;
  schemas_visible?: number | null;
  latency_ms?: number | null;
  error?: string | null;
}

export interface LakebaseInstanceOut {
  instance_name: string;
  state: string;
  capacity?: string | null;
  pg_version?: string | null;
  read_write_dns?: string | null;
  uid?: string | null;
}

export const useListLakebaseInstancesSuspense = (s?: Selector<LakebaseInstanceOut[]>) =>
  useSuspenseQuery({
    queryKey: ["listLakebaseInstances"],
    queryFn: () => api.get<LakebaseInstanceOut[]>("/lakebase/instances"),
    select: (r) => r.data,
    ...s?.query,
  });

export const useListSandboxesSuspense = (s?: Selector<SandboxListOut[]>) =>
  useSuspenseQuery({
    queryKey: ["listSandboxes"],
    queryFn: () => api.get<SandboxListOut[]>("/lakebase/sandboxes"),
    select: (r) => r.data,
    ...s?.query,
  });

export const useGetSandboxSuspense = (id: string, s?: Selector<SandboxOut>) =>
  useSuspenseQuery({
    queryKey: ["getSandbox", id],
    queryFn: () => api.get<SandboxOut>(`/lakebase/sandboxes/${encodeURIComponent(id)}`),
    select: (r) => r.data,
    ...s?.query,
  });

export const useListSandboxSchemasSuspense = (id: string, s?: Selector<string[]>) =>
  useSuspenseQuery({
    queryKey: ["listSandboxSchemas", id],
    queryFn: () => api.get<string[]>(`/lakebase/sandboxes/${encodeURIComponent(id)}/schemas`),
    select: (r) => r.data,
    ...s?.query,
  });

export const useCreateSandbox = (opts?: Opts<SandboxOut, { data: SandboxIn }>) =>
  useMutation({
    mutationFn: async ({ data }) =>
      (await api.post<SandboxOut>("/lakebase/sandboxes", data)).data,
    ...opts?.mutation,
  });

export const useTestSandbox = (opts?: Opts<SandboxTestResult, { sandboxId: string }>) =>
  useMutation({
    mutationFn: async ({ sandboxId }) =>
      (await api.post<SandboxTestResult>(`/lakebase/sandboxes/${encodeURIComponent(sandboxId)}/test`)).data,
    ...opts?.mutation,
  });

export const useDeactivateSandbox = (
  opts?: Opts<{ deactivated: string }, { sandboxId: string }>,
) =>
  useMutation({
    mutationFn: async ({ sandboxId }) =>
      (await api.delete<{ deactivated: string }>(`/lakebase/sandboxes/${encodeURIComponent(sandboxId)}`)).data,
    ...opts?.mutation,
  });

// ─── Extractions (M2 — Reverse Engineering) ──────────────────────────────────

export type SourceKind = "LAKEBASE" | "DDL_FILE" | "EMBARCADERO" | "ODBC" | "REST";
export type ExtractionStatus = "RUNNING" | "SUCCESS" | "PARTIAL" | "FAILED";

export interface ExtractedAttribute {
  technical_name: string;
  ordinal_position?: number | null;
  native_data_type?: string | null;
  is_nullable?: boolean | null;
  default_value?: string | null;
  is_primary_key: boolean;
  native_comment?: string | null;
}

export interface ExtractedEntity {
  schema_name: string;
  technical_name: string;
  entity_type: "TABLE" | "VIEW" | "MATERIALIZED_VIEW" | "EXTERNAL";
  native_comment?: string | null;
  row_count_approx?: number | null;
  attributes: ExtractedAttribute[];
}

export interface ExtractionSnapshot {
  source_kind: SourceKind;
  sandbox_id?: string | null;
  connection_id?: string | null;
  system_id: string;
  captured_at: string;
  schemas: string[];
  entities: ExtractedEntity[];
}

export interface ExtractionListOut {
  extraction_id: string;
  source_kind: SourceKind;
  system_id: string;
  system_name?: string | null;
  status: ExtractionStatus;
  started_at: string;
  ended_at?: string | null;
  duration_ms?: number | null;
  objects_found?: number | null;
  objects_new?: number | null;
  objects_changed?: number | null;
  objects_removed?: number | null;
  ticket_id?: string | null;
  created_by: string;
}

export interface ExtractionOut extends ExtractionListOut {
  connection_id?: string | null;
  lakebase_sandbox_id?: string | null;
  requested_schemas?: string | null;
  requested_kinds?: string | null;
  error_summary?: string | null;
  snapshot?: ExtractionSnapshot | null;
  diff_summary?: Record<string, number> | null;
}

export interface LakebaseExtractionIn {
  sandbox_id: string;
  system_id: string;
  schemas: string[];
  object_kinds: ("TABLE" | "VIEW")[];
  open_ticket: boolean;
}

export interface DDLImportIn {
  system_id: string;
  dialect: string;
  ddl_text: string;
  open_ticket: boolean;
}

export interface ExtractionResult {
  extraction_id: string;
  status: ExtractionStatus;
  objects_found: number;
  objects_new: number;
  objects_changed: number;
  objects_removed: number;
  duration_ms: number;
  ticket_id?: string | null;
  summary_md: string;
  errors: string[];
}

export const useListExtractionsSuspense = (
  params: { systemId?: string } = {},
  s?: Selector<ExtractionListOut[]>,
) =>
  useSuspenseQuery({
    queryKey: ["listExtractions", params],
    queryFn: () =>
      api.get<ExtractionListOut[]>("/extractions", {
        params: { system_id: params.systemId },
      }),
    select: (r) => r.data,
    ...s?.query,
  });

export const useGetExtractionSuspense = (id: string, s?: Selector<ExtractionOut>) =>
  useSuspenseQuery({
    queryKey: ["getExtraction", id],
    queryFn: () => api.get<ExtractionOut>(`/extractions/${encodeURIComponent(id)}`),
    select: (r) => r.data,
    ...s?.query,
  });

export const useRunLakebaseExtraction = (
  opts?: Opts<ExtractionResult, { data: LakebaseExtractionIn }>,
) =>
  useMutation({
    mutationFn: async ({ data }) =>
      (await api.post<ExtractionResult>("/extractions/lakebase/run", data)).data,
    ...opts?.mutation,
  });

export const useRunDDLImport = (
  opts?: Opts<ExtractionResult, { data: DDLImportIn }>,
) =>
  useMutation({
    mutationFn: async ({ data }) =>
      (await api.post<ExtractionResult>("/extractions/ddl/run", data)).data,
    ...opts?.mutation,
  });

// ─── Unity Catalog browse + extraction (M2 — Reverse Engineering) ────────────

export interface UCColumnOut {
  name: string;
  type_text: string;
  nullable: boolean;
  position: number;
}

export interface UCCatalogOut {
  name: string;
  comment?: string | null;
}

export interface UCSchemaOut {
  name: string;
  catalog_name: string;
  comment?: string | null;
}

export interface UCTableOut {
  name: string;
  catalog_name: string;
  schema_name: string;
  table_type: string;
  comment?: string | null;
  columns?: UCColumnOut[];
}

export interface UCExtractionIn {
  system_id: string;
  catalog: string;
  schema: string;
  table_names: string[];
  open_ticket: boolean;
}

export const useListUCCatalogsSuspense = (s?: Selector<UCCatalogOut[]>) =>
  useSuspenseQuery({
    queryKey: ["listUCCatalogs"],
    queryFn: () => api.get<UCCatalogOut[]>("/uc/catalogs"),
    select: (r) => r.data,
    ...s?.query,
  });

export const useListUCSchemasSuspense = (
  catalog: string,
  s?: Selector<UCSchemaOut[]>,
) =>
  useSuspenseQuery({
    queryKey: ["listUCSchemas", catalog],
    queryFn: () =>
      api.get<UCSchemaOut[]>(
        `/uc/catalogs/${encodeURIComponent(catalog)}/schemas`,
      ),
    select: (r) => r.data,
    ...s?.query,
  });

// Variantes não-suspense — usadas nos dropdowns do Sync (catálogo/schema destino),
// para não suspender o formulário inteiro e degradar bem se o SP não puder listar.
export const useUCCatalogs = () =>
  useQuery({
    queryKey: ["listUCCatalogs"],
    queryFn: () => api.get<UCCatalogOut[]>("/uc/catalogs").then((r) => r.data),
  });

export const useUCSchemas = (catalog: string | null | undefined) =>
  useQuery({
    queryKey: ["listUCSchemas", catalog],
    queryFn: () =>
      api
        .get<UCSchemaOut[]>(`/uc/catalogs/${encodeURIComponent(catalog!)}/schemas`)
        .then((r) => r.data),
    enabled: !!catalog,
  });

export const useListUCTablesSuspense = (
  catalog: string,
  schema: string,
  s?: Selector<UCTableOut[]>,
) =>
  useSuspenseQuery({
    queryKey: ["listUCTables", catalog, schema],
    queryFn: () =>
      api.get<UCTableOut[]>(
        `/uc/catalogs/${encodeURIComponent(catalog)}/schemas/${encodeURIComponent(schema)}/tables`,
      ),
    select: (r) => r.data,
    ...s?.query,
  });

export const useRunUCExtraction = (
  opts?: Opts<ExtractionResult, { data: UCExtractionIn }>,
) =>
  useMutation({
    mutationFn: async ({ data }) =>
      (await api.post<ExtractionResult>("/extractions/uc/run", data)).data,
    ...opts?.mutation,
  });

// ─── Lineage (Módulo 7) ──────────────────────────────────────────────────────

export type IntegrationType = "CDC" | "BATCH" | "API_PULL" | "API_PUSH" | "FILE";
export type Periodicity = "REAL_TIME" | "DAILY" | "WEEKLY" | "MONTHLY" | "ON_DEMAND";
export type ConsumptionType = "DIRECT_READ" | "API" | "REPORT" | "ML_MODEL";
export type SLALevel = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export interface UpstreamIn {
  entity_id: string;
  source_system: string;
  source_entity?: string | null;
  integration_type?: IntegrationType | null;
  periodicity?: Periodicity | null;
  transformations?: string | null;
  pipeline_link?: string | null;
}

export interface UpstreamOut {
  lineage_id: string;
  entity_id: string;
  source_system: string;
  source_entity?: string | null;
  integration_type?: IntegrationType | null;
  periodicity?: Periodicity | null;
  transformations?: string | null;
  pipeline_link?: string | null;
  created_at: string;
  created_by: string;
  updated_at: string;
  updated_by: string;
}

export interface DownstreamIn {
  entity_id: string;
  consumer_system: string;
  consumption_type?: ConsumptionType | null;
  responsible_team?: string | null;
  sla_dependency?: SLALevel | null;
  detected_via?: "MANUAL" | "UC_LINEAGE";
}

export interface DownstreamOut {
  consumer_id: string;
  entity_id: string;
  consumer_system: string;
  consumption_type?: ConsumptionType | null;
  responsible_team?: string | null;
  sla_dependency?: SLALevel | null;
  detected_via: "MANUAL" | "UC_LINEAGE";
  created_at: string;
  created_by: string;
  updated_at: string;
  updated_by: string;
}

export interface LineageGraphNode {
  id: string;
  label: string;
  kind: "entity" | "upstream_system" | "downstream_system";
  schema_name?: string | null;
  system_name?: string | null;
  domain?: string | null;
  entity_type?: string | null;
}

export interface LineageGraphEdge {
  source: string;
  target: string;
  edge_kind: "upstream" | "downstream";
  label?: string | null;
  sla_dependency?: SLALevel | null;
}

export interface LineageGraph {
  center_entity_id: string;
  nodes: LineageGraphNode[];
  edges: LineageGraphEdge[];
  depth: number;
}

export const useListUpstreamSuspense = (entityId: string, s?: Selector<UpstreamOut[]>) =>
  useSuspenseQuery({
    queryKey: ["listUpstream", entityId],
    queryFn: () =>
      api.get<UpstreamOut[]>(`/lineage/entities/${encodeURIComponent(entityId)}/upstream`),
    select: (r) => r.data,
    ...s?.query,
  });

export const useListDownstreamSuspense = (entityId: string, s?: Selector<DownstreamOut[]>) =>
  useSuspenseQuery({
    queryKey: ["listDownstream", entityId],
    queryFn: () =>
      api.get<DownstreamOut[]>(`/lineage/entities/${encodeURIComponent(entityId)}/downstream`),
    select: (r) => r.data,
    ...s?.query,
  });

export const useLineageGraphSuspense = (
  entityId: string,
  depth: number = 1,
  s?: Selector<LineageGraph>,
) =>
  useSuspenseQuery({
    queryKey: ["lineageGraph", entityId, depth],
    queryFn: () =>
      api.get<LineageGraph>(`/lineage/entities/${encodeURIComponent(entityId)}/graph`, {
        params: { depth },
      }),
    select: (r) => r.data,
    ...s?.query,
  });

export const useCreateUpstream = (
  opts?: Opts<UpstreamOut, { entityId: string; data: UpstreamIn }>,
) =>
  useMutation({
    mutationFn: async ({ entityId, data }) =>
      (await api.post<UpstreamOut>(
        `/lineage/entities/${encodeURIComponent(entityId)}/upstream`,
        data,
      )).data,
    ...opts?.mutation,
  });

export const useDeleteUpstream = (opts?: Opts<{ deleted: string }, { lineageId: string }>) =>
  useMutation({
    mutationFn: async ({ lineageId }) =>
      (await api.delete<{ deleted: string }>(`/lineage/upstream/${encodeURIComponent(lineageId)}`)).data,
    ...opts?.mutation,
  });

export const useCreateDownstream = (
  opts?: Opts<DownstreamOut, { entityId: string; data: DownstreamIn }>,
) =>
  useMutation({
    mutationFn: async ({ entityId, data }) =>
      (await api.post<DownstreamOut>(
        `/lineage/entities/${encodeURIComponent(entityId)}/downstream`,
        data,
      )).data,
    ...opts?.mutation,
  });

export const useDeleteDownstream = (
  opts?: Opts<{ deleted: string }, { consumerId: string }>,
) =>
  useMutation({
    mutationFn: async ({ consumerId }) =>
      (await api.delete<{ deleted: string }>(`/lineage/downstream/${encodeURIComponent(consumerId)}`)).data,
    ...opts?.mutation,
  });

// ─── Editorial Sessions (modelo "ticket de sessão") ──────────────────────────

/**
 * SessionStatusOut: resumo do ticket aberto da sessão atual do usuário em um
 * dado sistema. Backend retorna `null` quando não há sessão ativa — o select
 * normaliza pra `SessionStatusOut | null` no consumidor.
 */
export interface SessionStatusOut {
  ticket_id: string;
  additions: number;
  removals: number;
  changes: number;
}

// ─── Dashboard ───────────────────────────────────────────────────────────────

export interface DashboardEnvCount {
  environment: SystemEnvironment | null;
  count: number;
}

export interface DashboardTicketStats {
  open: number;
  approved: number;
  applied: number;
  rejected: number;
}

export interface DashboardRecentItem {
  kind: string;
  id: string;
  label: string;
  actor?: string | null;
  at?: string | null;
  status?: string | null;
}

export interface DashboardSummary {
  systems_total: number;
  systems_active: number;
  systems_by_env: DashboardEnvCount[];
  entities_total: number;
  entities_shared: number;
  attributes_total: number;
  relationships_total: number;
  tickets: DashboardTicketStats;
  extractions_last_7d: number;
  recent: DashboardRecentItem[];
}

export const useDashboardSummarySuspense = (s?: Selector<DashboardSummary>) =>
  useSuspenseQuery({
    queryKey: ["dashboardSummary"],
    queryFn: () => api.get<DashboardSummary>("/dashboard/summary"),
    select: (r) => r.data,
    ...s?.query,
  });

/**
 * Lê o status do ticket de sessão atual para um sistema. Retorna `null` quando
 * o backend responder sem sessão ativa — não dispara erro nesse caso.
 */
export const useGetSessionStatusSuspense = (
  systemId: string,
  s?: Selector<SessionStatusOut | null>,
) =>
  useSuspenseQuery({
    queryKey: ["getSessionStatus", systemId],
    queryFn: () =>
      api.get<SessionStatusOut | null>("/sessions/current", {
        params: { system_id: systemId },
        // 404 ou null body — devolve null em vez de jogar erro.
        validateStatus: (st) => (st >= 200 && st < 300) || st === 404,
      }),
    select: (r) => (r.status === 404 ? null : (r.data ?? null)),
    ...s?.query,
  });

/**
 * Descarta a sessão atual (apaga o ticket OPEN do usuário no sistema).
 */
export const useDiscardSession = (
  opts?: Opts<{ discarded: string | null }, { systemId?: string } | void>,
) =>
  useMutation({
    mutationFn: async (vars) => {
      const systemId =
        vars && "systemId" in (vars as Record<string, unknown>)
          ? (vars as { systemId?: string }).systemId
          : undefined;
      return (
        await api.post<{ discarded: string | null }>(
          "/sessions/discard",
          {},
          { params: systemId ? { system_id: systemId } : undefined },
        )
      ).data;
    },
    ...opts?.mutation,
  });

// ─── Diagram (Módulo 4 — DER) ────────────────────────────────────────────────

export interface DiagramAttribute {
  attribute_id: string;
  technical_name: string;
  logical_name?: string | null;
  native_data_type?: string | null;
  is_primary_key: boolean;
  is_nullable?: boolean | null;
  ordinal_position?: number | null;
  has_lgpd_flag: boolean;
  is_indexed?: boolean;
  // Editorial session — atributo com mudança pendente
  pending_op?: "add" | "change" | "remove" | null;
  pending_ticket_id?: string | null;
}

export interface DiagramIndexSummary {
  index_name: string;
  index_type: string;
  is_unique: boolean;
  columns: string[];
}

export interface DiagramEntity {
  entity_id: string;
  system_id: string;
  schema_name: string;
  technical_name: string;
  logical_name?: string | null;
  entity_type: "TABLE" | "VIEW" | "MATERIALIZED_VIEW" | "EXTERNAL";
  domain?: string | null;
  criticality?: string | null;
  attributes: DiagramAttribute[];
  has_lgpd_flag: boolean;
  // Storage badges (F5): contagem de índices + estratégia de partição
  indexes_count?: number;
  partition_strategy?: "RANGE" | "LIST" | "HASH" | "LIQUID" | "NONE" | null;
  // F9: lista completa de índices + colunas de partição pro DER
  indexes?: DiagramIndexSummary[];
  partition_columns?: string[];
  // Editorial session — entidade com mudança pendente no ticket atual
  pending_op?: "add" | "change" | "remove" | null;
  pending_ticket_id?: string | null;
}

export interface DiagramRelationship {
  relationship_id: string;
  source_entity_id: string;
  target_entity_id: string;
  rel_type?: string | null;
  source_cardinality?: string | null;
  target_cardinality?: string | null;
  source_attrs: string[];
  target_attrs: string[];
  description?: string | null;
  origin?: string | null;
}

export interface NodePosition {
  x: number;
  y: number;
}

export interface DiagramView {
  system_id: string;
  system_name?: string | null;
  entities: DiagramEntity[];
  relationships: DiagramRelationship[];
  layout: Record<string, NodePosition>;
  layout_name: string;
}

export interface LayoutSaveIn {
  layout_name: string;
  positions: Record<string, NodePosition>;
}

export interface LayoutOut {
  layout_id: string;
  system_id: string;
  layout_name: string;
  positions: Record<string, NodePosition>;
  created_at: string;
  created_by: string;
  updated_at: string;
  updated_by: string;
}

export const useGetDiagramSuspense = (
  systemId: string,
  layoutName: string = "default",
  s?: Selector<DiagramView>,
) =>
  useSuspenseQuery({
    queryKey: ["getDiagram", systemId, layoutName],
    queryFn: () =>
      api.get<DiagramView>(`/diagram/${encodeURIComponent(systemId)}`, {
        params: { layout_name: layoutName },
      }),
    select: (r) => r.data,
    ...s?.query,
  });

export const useSaveLayout = (
  opts?: Opts<LayoutOut, { systemId: string; data: LayoutSaveIn }>,
) =>
  useMutation({
    mutationFn: async ({ systemId, data }) =>
      (await api.post<LayoutOut>(
        `/diagram/${encodeURIComponent(systemId)}/layout`,
        data,
      )).data,
    ...opts?.mutation,
  });

export const useListLayoutNamesSuspense = (systemId: string, s?: Selector<string[]>) =>
  useSuspenseQuery({
    queryKey: ["listLayoutNames", systemId],
    queryFn: () => api.get<string[]>(`/diagram/${encodeURIComponent(systemId)}/layouts`),
    select: (r) => r.data,
    ...s?.query,
  });

export const useDeleteLayout = (
  opts?: Opts<{ deleted: string }, { systemId: string; layoutName: string }>,
) =>
  useMutation({
    mutationFn: async ({ systemId, layoutName }) =>
      (await api.delete<{ deleted: string }>(
        `/diagram/${encodeURIComponent(systemId)}/layouts/${encodeURIComponent(layoutName)}`,
      )).data,
    ...opts?.mutation,
  });

// ─── Embarcadero ER/Studio (.DM1) import ─────────────────────────────────────

export interface EmbarcaderoImportIn {
  system_id: string;
  dm1_text: string;
  open_ticket: boolean;
}

export const useRunEmbarcaderoImport = (
  opts?: Opts<ExtractionResult, { data: EmbarcaderoImportIn }>,
) =>
  useMutation({
    mutationFn: async ({ data }) =>
      (await api.post<ExtractionResult>("/extractions/embarcadero/run", data)).data,
    ...opts?.mutation,
  });

// ─── Relationships (Módulo 3+) ───────────────────────────────────────────────

export type RelType = "1:1" | "1:N" | "N:M" | "INHERIT";
export type Cardinality = "OPTIONAL" | "MANDATORY";
export type FKRule =
  | "NO ACTION"
  | "CASCADE"
  | "SET NULL"
  | "SET DEFAULT"
  | "RESTRICT";
export type RelationshipOrigin = "EXTRACTED" | "MANUAL";

export interface RelationshipIn {
  system_id: string;
  source_entity_id: string;
  target_entity_id: string;
  source_attr_ids?: string[];
  target_attr_ids?: string[];
  rel_type?: RelType;
  source_cardinality?: Cardinality;
  target_cardinality?: Cardinality;
  description?: string | null;
  fk_update_rule?: FKRule | null;
  fk_delete_rule?: FKRule | null;
}

export interface RelationshipListOut {
  relationship_id: string;
  system_id: string;
  system_name?: string | null;
  source_entity_id: string;
  source_entity_label?: string | null;
  target_entity_id: string;
  target_entity_label?: string | null;
  rel_type?: RelType | null;
  source_cardinality?: Cardinality | null;
  target_cardinality?: Cardinality | null;
  origin?: RelationshipOrigin | null;
  description?: string | null;
  updated_at: string;
}

export interface RelationshipOut extends RelationshipListOut {
  source_attr_ids: string[];
  target_attr_ids: string[];
  fk_update_rule?: FKRule | null;
  fk_delete_rule?: FKRule | null;
  created_at: string;
  created_by: string;
  updated_by: string;
}

export const useListRelationshipsSuspense = (
  params: { systemId?: string } = {},
  s?: Selector<RelationshipListOut[]>,
) =>
  useSuspenseQuery({
    queryKey: ["listRelationships", params],
    queryFn: () =>
      api.get<RelationshipListOut[]>("/relationships", {
        params: { system_id: params.systemId },
      }),
    select: (r) => r.data,
    ...s?.query,
  });

export const useGetRelationshipSuspense = (
  id: string,
  s?: Selector<RelationshipOut>,
) =>
  useSuspenseQuery({
    queryKey: ["getRelationship", id],
    queryFn: () =>
      api.get<RelationshipOut>(`/relationships/${encodeURIComponent(id)}`),
    select: (r) => r.data,
    ...s?.query,
  });

export const useCreateRelationship = (
  opts?: Opts<RelationshipOut, { data: RelationshipIn }>,
) =>
  useMutation({
    mutationFn: async ({ data }) =>
      (await api.post<RelationshipOut>("/relationships", data)).data,
    ...opts?.mutation,
  });

export const useUpdateRelationship = (
  opts?: Opts<
    RelationshipOut,
    { relationshipId: string; data: RelationshipIn }
  >,
) =>
  useMutation({
    mutationFn: async ({ relationshipId, data }) =>
      (
        await api.put<RelationshipOut>(
          `/relationships/${encodeURIComponent(relationshipId)}`,
          data,
        )
      ).data,
    ...opts?.mutation,
  });

export const useDeleteRelationship = (
  opts?: Opts<{ deleted: string }, { relationshipId: string }>,
) =>
  useMutation({
    mutationFn: async ({ relationshipId }) =>
      (
        await api.delete<{ deleted: string }>(
          `/relationships/${encodeURIComponent(relationshipId)}`,
        )
      ).data,
    ...opts?.mutation,
  });

// ─── Global Search ────────────────────────────────────────────────────────────

export type SearchKind =
  | "entity"
  | "attribute"
  | "term"
  | "flag"
  | "ticket"
  | "connection"
  | "system";

export interface SearchResult {
  kind: SearchKind;
  id: string;
  label: string;
  sublabel?: string | null;
  path: string;
}

export interface SearchResults {
  q: string;
  total: number;
  results: SearchResult[];
}

/**
 * Global search hook. Returns empty results immediately when the query is
 * shorter than 2 chars to avoid hitting the backend on every keystroke.
 */
export const useGlobalSearch = (q: string, limit = 20) => {
  const enabled = (q?.trim().length ?? 0) >= 2;
  return useQuery({
    queryKey: ["globalSearch", q, limit],
    queryFn: () =>
      api
        .get<SearchResults>("/search", { params: { q, limit } })
        .then((r) => r.data),
    enabled,
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  });
};

// ─── Audit ────────────────────────────────────────────────────────────────────

export interface AuditEntry {
  audit_id: string;
  occurred_at: string;
  actor_email: string;
  actor_role?: string | null;
  action: string;
  object_type: string;
  object_id?: string | null;
  request_id?: string | null;
  client_ip?: string | null;
}

export interface AuditDetailEntry extends AuditEntry {
  before_json?: string | null;
  after_json?: string | null;
  user_agent?: string | null;
}

export interface AuditCount {
  key: string;
  count: number;
}

export interface AuditStats {
  since: string;
  until: string;
  by_action: AuditCount[];
  by_object_type: AuditCount[];
  total: number;
}

export interface AuditListParams {
  actor_email?: string;
  action?: string;
  object_type?: string;
  object_id?: string;
  since?: string;
  limit?: number;
}

export const useListAuditSuspense = (
  params: AuditListParams = {},
  s?: Selector<AuditEntry[]>,
) =>
  useSuspenseQuery({
    queryKey: ["listAudit", params],
    queryFn: () =>
      api.get<AuditEntry[]>("/audit", {
        params: {
          actor_email: params.actor_email || undefined,
          action: params.action || undefined,
          object_type: params.object_type || undefined,
          object_id: params.object_id || undefined,
          since: params.since || undefined,
          limit: params.limit ?? 200,
        },
      }),
    select: (r) => r.data,
    ...s?.query,
  });

export const useGetAuditDetailSuspense = (
  auditId: string,
  s?: Selector<AuditDetailEntry>,
) =>
  useSuspenseQuery({
    queryKey: ["getAuditDetail", auditId],
    queryFn: () =>
      api.get<AuditDetailEntry>(`/audit/${encodeURIComponent(auditId)}`),
    select: (r) => r.data,
    ...s?.query,
  });

export type RiskLevel = "CRITICAL" | "MODERATE" | "LOW";
export type EventType = "INSERT" | "UPDATE" | "DELETE";
export type TriggerTiming = "BEFORE" | "AFTER" | "INSTEAD_OF";

export interface ViewIn {
  view_entity_id: string;
  purpose?: string | null;
  definition_sql?: string | null;
  base_entity_ids?: string[];
}
export interface ViewOut {
  view_entity_id: string;
  entity_label?: string | null;
  system_id?: string | null;
  system_name?: string | null;
  purpose?: string | null;
  definition_sql?: string | null;
  base_entity_ids: string[];
  created_at?: string | null;
  created_by?: string | null;
  updated_at?: string | null;
  updated_by?: string | null;
}

export const useListViewsSuspense = (systemId?: string, s?: Selector<ViewOut[]>) =>
  useSuspenseQuery({
    queryKey: ["listViews", systemId ?? null],
    queryFn: () => api.get<ViewOut[]>("/views", { params: { system_id: systemId } }),
    select: (r) => r.data,
    ...s?.query,
  });

export const useGetViewSuspense = (viewEntityId: string, s?: Selector<ViewOut>) =>
  useSuspenseQuery({
    queryKey: ["getView", viewEntityId],
    queryFn: () => api.get<ViewOut>(`/views/${encodeURIComponent(viewEntityId)}`),
    select: (r) => r.data,
    ...s?.query,
  });

export const useUpsertView = (
  opts?: Opts<ViewOut, { viewEntityId: string; data: ViewIn }>,
) =>
  useMutation({
    mutationFn: async ({ viewEntityId, data }) =>
      (await api.put<ViewOut>(`/views/${encodeURIComponent(viewEntityId)}`, data)).data,
    ...opts?.mutation,
  });

export interface ProcedureParam {
  name: string;
  type: string;
  direction?: "IN" | "OUT" | "INOUT";
  description?: string | null;
}
export interface ProcedureIn {
  system_id: string;
  schema_name: string;
  technical_name: string;
  logical_name?: string | null;
  behavior_desc?: string | null;
  parameters?: ProcedureParam[];
  source_code?: string | null;
  dependent_systems?: string[];
  change_risk_level?: RiskLevel | null;
}
export interface ProcedureListOut {
  procedure_id: string;
  system_id: string;
  system_name?: string | null;
  schema_name: string;
  technical_name: string;
  logical_name?: string | null;
  change_risk_level?: RiskLevel | null;
  updated_at: string;
}
export interface ProcedureOut extends ProcedureListOut {
  behavior_desc?: string | null;
  parameters: ProcedureParam[];
  source_code?: string | null;
  dependent_systems: string[];
  created_at: string;
  created_by: string;
  updated_by: string;
}

export const useListProceduresSuspense = (systemId?: string, s?: Selector<ProcedureListOut[]>) =>
  useSuspenseQuery({
    queryKey: ["listProcedures", systemId ?? null],
    queryFn: () => api.get<ProcedureListOut[]>("/procedures", { params: { system_id: systemId } }),
    select: (r) => r.data,
    ...s?.query,
  });

export const useGetProcedureSuspense = (id: string, s?: Selector<ProcedureOut>) =>
  useSuspenseQuery({
    queryKey: ["getProcedure", id],
    queryFn: () => api.get<ProcedureOut>(`/procedures/${encodeURIComponent(id)}`),
    select: (r) => r.data,
    ...s?.query,
  });

export const useCreateProcedure = (opts?: Opts<ProcedureOut, { data: ProcedureIn }>) =>
  useMutation({
    mutationFn: async ({ data }) => (await api.post<ProcedureOut>("/procedures", data)).data,
    ...opts?.mutation,
  });

export const useUpdateProcedure = (
  opts?: Opts<ProcedureOut, { procedureId: string; data: ProcedureIn }>,
) =>
  useMutation({
    mutationFn: async ({ procedureId, data }) =>
      (await api.put<ProcedureOut>(`/procedures/${encodeURIComponent(procedureId)}`, data)).data,
    ...opts?.mutation,
  });

export const useDeleteProcedure = (opts?: Opts<{ deleted: string }, { procedureId: string }>) =>
  useMutation({
    mutationFn: async ({ procedureId }) =>
      (await api.delete<{ deleted: string }>(`/procedures/${encodeURIComponent(procedureId)}`)).data,
    ...opts?.mutation,
  });

export interface TriggerIn {
  system_id: string;
  schema_name: string;
  technical_name: string;
  associated_entity_id?: string | null;
  event_type?: EventType | null;
  timing?: TriggerTiming | null;
  body?: string | null;
  behavior_desc?: string | null;
  change_risk_level?: RiskLevel | null;
}
export interface TriggerListOut {
  trigger_id: string;
  system_id: string;
  system_name?: string | null;
  schema_name: string;
  technical_name: string;
  associated_entity_id?: string | null;
  associated_entity_label?: string | null;
  event_type?: EventType | null;
  timing?: TriggerTiming | null;
  change_risk_level?: RiskLevel | null;
  updated_at: string;
}
export interface TriggerOut extends TriggerListOut {
  body?: string | null;
  behavior_desc?: string | null;
  created_at: string;
  created_by: string;
  updated_by: string;
}

export const useListTriggersSuspense = (systemId?: string, s?: Selector<TriggerListOut[]>) =>
  useSuspenseQuery({
    queryKey: ["listTriggers", systemId ?? null],
    queryFn: () => api.get<TriggerListOut[]>("/triggers", { params: { system_id: systemId } }),
    select: (r) => r.data,
    ...s?.query,
  });

export const useGetTriggerSuspense = (id: string, s?: Selector<TriggerOut>) =>
  useSuspenseQuery({
    queryKey: ["getTrigger", id],
    queryFn: () => api.get<TriggerOut>(`/triggers/${encodeURIComponent(id)}`),
    select: (r) => r.data,
    ...s?.query,
  });

export const useCreateTrigger = (opts?: Opts<TriggerOut, { data: TriggerIn }>) =>
  useMutation({
    mutationFn: async ({ data }) => (await api.post<TriggerOut>("/triggers", data)).data,
    ...opts?.mutation,
  });

export const useUpdateTrigger = (
  opts?: Opts<TriggerOut, { triggerId: string; data: TriggerIn }>,
) =>
  useMutation({
    mutationFn: async ({ triggerId, data }) =>
      (await api.put<TriggerOut>(`/triggers/${encodeURIComponent(triggerId)}`, data)).data,
    ...opts?.mutation,
  });

export const useDeleteTrigger = (opts?: Opts<{ deleted: string }, { triggerId: string }>) =>
  useMutation({
    mutationFn: async ({ triggerId }) =>
      (await api.delete<{ deleted: string }>(`/triggers/${encodeURIComponent(triggerId)}`)).data,
    ...opts?.mutation,
  });

export interface SequenceIn {
  system_id: string;
  schema_name: string;
  technical_name: string;
  logical_name?: string | null;
  description_md?: string | null;
  start_value?: number | null;
  increment_by?: number | null;
  min_value?: number | null;
  max_value?: number | null;
  cache_size?: number | null;
  is_cycle?: boolean | null;
  current_value?: number | null;
  used_by_entity_ids?: string[];
}
export interface SequenceListOut {
  sequence_id: string;
  system_id: string;
  system_name?: string | null;
  schema_name: string;
  technical_name: string;
  logical_name?: string | null;
  increment_by?: number | null;
  current_value?: number | null;
  updated_at: string;
}
export interface SequenceOut extends SequenceListOut {
  description_md?: string | null;
  start_value?: number | null;
  min_value?: number | null;
  max_value?: number | null;
  cache_size?: number | null;
  is_cycle?: boolean | null;
  used_by_entity_ids: string[];
  native_comment?: string | null;
  created_at: string;
  created_by: string;
  updated_by: string;
}

export const useListSequencesSuspense = (systemId?: string, s?: Selector<SequenceListOut[]>) =>
  useSuspenseQuery({
    queryKey: ["listSequences", systemId ?? null],
    queryFn: () => api.get<SequenceListOut[]>("/sequences", { params: { system_id: systemId } }),
    select: (r) => r.data,
    ...s?.query,
  });

export const useGetSequenceSuspense = (id: string, s?: Selector<SequenceOut>) =>
  useSuspenseQuery({
    queryKey: ["getSequence", id],
    queryFn: () => api.get<SequenceOut>(`/sequences/${encodeURIComponent(id)}`),
    select: (r) => r.data,
    ...s?.query,
  });

export const useCreateSequence = (opts?: Opts<SequenceOut, { data: SequenceIn }>) =>
  useMutation({
    mutationFn: async ({ data }) => (await api.post<SequenceOut>("/sequences", data)).data,
    ...opts?.mutation,
  });

export const useUpdateSequence = (
  opts?: Opts<SequenceOut, { sequenceId: string; data: SequenceIn }>,
) =>
  useMutation({
    mutationFn: async ({ sequenceId, data }) =>
      (await api.put<SequenceOut>(`/sequences/${encodeURIComponent(sequenceId)}`, data)).data,
    ...opts?.mutation,
  });

export const useDeleteSequence = (opts?: Opts<{ deleted: string }, { sequenceId: string }>) =>
  useMutation({
    mutationFn: async ({ sequenceId }) =>
      (await api.delete<{ deleted: string }>(`/sequences/${encodeURIComponent(sequenceId)}`)).data,
    ...opts?.mutation,
  });
export const useAuditStatsSuspense = (days = 7, s?: Selector<AuditStats>) =>
  useSuspenseQuery({
    queryKey: ["auditStats", days],
    queryFn: () => api.get<AuditStats>("/audit/stats", { params: { days } }),
    select: (r) => r.data,
    ...s?.query,
  });

// ─── Diagram: quick-add entity + validate-source ─────────────────────────────

export interface QuickEntityIn {
  system_id: string;
  schema_name: string;
  technical_name: string;
  logical_name?: string | null;
  entity_type?: "TABLE" | "VIEW" | "MATERIALIZED_VIEW" | "EXTERNAL";
  domain?: string | null;
  initial_attributes?: Array<{
    technical_name: string;
    native_data_type?: string | null;
    is_primary_key?: boolean;
    is_nullable?: boolean;
    logical_name?: string | null;
    default_value?: string | null;
  }>;
}

export interface SourceCheckResult {
  entity_id: string;
  schema_name: string;
  technical_name: string;
  exists_in_source: boolean;
  source_kind: "UC_DELTA" | "LAKEBASE" | "UNKNOWN";
  source_catalog?: string | null;
  columns_in_source?: number | null;
  columns_in_catalog: number;
  missing_in_source: string[];
  extra_in_source: string[];
  error?: string | null;
}

export interface SourceValidationOut {
  system_id: string;
  system_name?: string | null;
  source_kind: string;
  target_catalog?: string | null;
  results: SourceCheckResult[];
  total_entities: number;
  found_count: number;
  missing_count: number;
}

export const useQuickAddEntity = (
  opts?: Opts<DiagramEntity, { systemId: string; data: QuickEntityIn }>,
) =>
  useMutation({
    mutationFn: async ({ systemId, data }) =>
      (await api.post<DiagramEntity>(
        `/diagram/${encodeURIComponent(systemId)}/entities`,
        data,
      )).data,
    ...opts?.mutation,
  });

export const useValidateSource = (
  opts?: Opts<
    SourceValidationOut,
    { systemId: string; targetCatalog?: string; sandboxId?: string }
  >,
) =>
  useMutation({
    mutationFn: async ({ systemId, targetCatalog, sandboxId }) =>
      (await api.post<SourceValidationOut>(
        `/diagram/${encodeURIComponent(systemId)}/validate-source`,
        {},
        { params: { target_catalog: targetCatalog, sandbox_id: sandboxId } },
      )).data,
    ...opts?.mutation,
  });

// ─── Schemas & Diagramas (M6) ──────────────────────────────────────────────
// Hooks adicionados à mão (espelhando o orval) — refresh_openapi canoniza
// quando rodar numa máquina com pypi liberado.

export interface SchemaIn {
  system_id: string;
  schema_name: string;
  logical_name?: string | null;
  domain?: string | null;
  owner_team?: string | null;
  description_md?: string | null;
  is_active?: boolean;
}

export interface SchemaOut {
  schema_id: string;
  system_id: string;
  schema_name: string;
  logical_name?: string | null;
  domain?: string | null;
  owner_team?: string | null;
  description_md?: string | null;
  is_active: boolean;
  created_at: string;
  created_by: string;
  updated_at: string;
  updated_by: string;
}

export interface SchemaListOut {
  schema_id: string;
  system_id: string;
  schema_name: string;
  logical_name?: string | null;
  domain?: string | null;
  is_active: boolean;
  entity_count: number;
  diagram_count: number;
}

export interface DiagramIn {
  system_id: string;
  schema_id: string;
  diagram_name: string;
  description?: string | null;
  is_default?: boolean;
}

export interface DiagramOut {
  diagram_id: string;
  system_id: string;
  schema_id: string;
  diagram_name: string;
  description?: string | null;
  is_default: boolean;
  created_at: string;
  created_by: string;
  updated_at: string;
  updated_by: string;
  entity_count: number;
}

export interface DiagramListOut {
  diagram_id: string;
  system_id: string;
  schema_id: string;
  diagram_name: string;
  is_default: boolean;
  entity_count: number;
}

export interface DiagramMemberOut {
  entity_id: string;
  schema_name?: string | null;
  technical_name?: string | null;
  logical_name?: string | null;
  pos_x?: number | null;
  pos_y?: number | null;
}

export interface DiagramDetailOut extends DiagramOut {
  members: DiagramMemberOut[];
}

export interface DiagramMemberIn {
  entity_id: string;
  pos_x?: number | null;
  pos_y?: number | null;
}

export interface DiagramMembersIn {
  members: DiagramMemberIn[];
}

export interface DiagramLayoutIn {
  positions: DiagramMemberIn[];
}

export const useListSchemasSuspense = (
  params: { systemId?: string } = {},
  s?: Selector<SchemaListOut[]>,
) =>
  useSuspenseQuery({
    queryKey: ["listSchemas", params],
    queryFn: () =>
      api.get<SchemaListOut[]>("/schemas", {
        params: { system_id: params.systemId },
      }),
    select: (r) => r.data,
    ...s?.query,
  });

export const useGetSchemaSuspense = (id: string, s?: Selector<SchemaOut>) =>
  useSuspenseQuery({
    queryKey: ["getSchema", id],
    queryFn: () => api.get<SchemaOut>(`/schemas/${encodeURIComponent(id)}`),
    select: (r) => r.data,
    ...s?.query,
  });

export const useCreateSchema = (opts?: Opts<SchemaOut, { data: SchemaIn }>) =>
  useMutation({
    mutationFn: async ({ data }) => (await api.post<SchemaOut>("/schemas", data)).data,
    ...opts?.mutation,
  });

export const useUpdateSchema = (
  opts?: Opts<SchemaOut, { schemaId: string; data: SchemaIn }>,
) =>
  useMutation({
    mutationFn: async ({ schemaId, data }) =>
      (await api.put<SchemaOut>(`/schemas/${encodeURIComponent(schemaId)}`, data)).data,
    ...opts?.mutation,
  });

export const useDeleteSchema = (opts?: Opts<{ deleted: string }, { schemaId: string }>) =>
  useMutation({
    mutationFn: async ({ schemaId }) =>
      (await api.delete<{ deleted: string }>(`/schemas/${encodeURIComponent(schemaId)}`)).data,
    ...opts?.mutation,
  });

export const useListDiagramsSuspense = (
  params: { schemaId?: string; systemId?: string } = {},
  s?: Selector<DiagramListOut[]>,
) =>
  useSuspenseQuery({
    queryKey: ["listDiagrams", params],
    queryFn: () =>
      api.get<DiagramListOut[]>("/diagrams", {
        params: { schema_id: params.schemaId, system_id: params.systemId },
      }),
    select: (r) => r.data,
    ...s?.query,
  });

export const useGetDiagramByIdSuspense = (id: string, s?: Selector<DiagramDetailOut>) =>
  useSuspenseQuery({
    queryKey: ["getDiagramById", id],
    queryFn: () => api.get<DiagramDetailOut>(`/diagrams/${encodeURIComponent(id)}`),
    select: (r) => r.data,
    ...s?.query,
  });

// Variante não-suspense (fetch condicional) — usada no canvas, onde o diagrama
// selecionado pode ser nulo (mostra todas as entities do schema).
export const useGetDiagramById = (id: string | null | undefined) =>
  useQuery({
    queryKey: ["getDiagramById", id],
    queryFn: () =>
      api.get<DiagramDetailOut>(`/diagrams/${encodeURIComponent(id!)}`).then((r) => r.data),
    enabled: !!id,
  });

export const useCreateDiagram = (opts?: Opts<DiagramOut, { data: DiagramIn }>) =>
  useMutation({
    mutationFn: async ({ data }) => (await api.post<DiagramOut>("/diagrams", data)).data,
    ...opts?.mutation,
  });

export const useUpdateDiagram = (
  opts?: Opts<DiagramOut, { diagramId: string; data: DiagramIn }>,
) =>
  useMutation({
    mutationFn: async ({ diagramId, data }) =>
      (await api.put<DiagramOut>(`/diagrams/${encodeURIComponent(diagramId)}`, data)).data,
    ...opts?.mutation,
  });

export const useDeleteDiagram = (opts?: Opts<{ deleted: string }, { diagramId: string }>) =>
  useMutation({
    mutationFn: async ({ diagramId }) =>
      (await api.delete<{ deleted: string }>(`/diagrams/${encodeURIComponent(diagramId)}`)).data,
    ...opts?.mutation,
  });

export const useSetDiagramMembers = (
  opts?: Opts<DiagramDetailOut, { diagramId: string; data: DiagramMembersIn }>,
) =>
  useMutation({
    mutationFn: async ({ diagramId, data }) =>
      (await api.put<DiagramDetailOut>(`/diagrams/${encodeURIComponent(diagramId)}/members`, data)).data,
    ...opts?.mutation,
  });

export const useSaveDiagramLayout = (
  opts?: Opts<DiagramDetailOut, { diagramId: string; data: DiagramLayoutIn }>,
) =>
  useMutation({
    mutationFn: async ({ diagramId, data }) =>
      (await api.put<DiagramDetailOut>(`/diagrams/${encodeURIComponent(diagramId)}/layout`, data)).data,
    ...opts?.mutation,
  });
