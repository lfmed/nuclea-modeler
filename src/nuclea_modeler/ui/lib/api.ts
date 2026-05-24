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
  useMutation,
  type UseSuspenseQueryOptions,
  type UseMutationOptions,
} from "@tanstack/react-query";
import axios, { type AxiosResponse } from "axios";

const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

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

export interface SystemListOut {
  system_id: string;
  system_name: string;
  domain?: string | null;
  technology?: string | null;
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

function suspenseHook<T>(key: readonly unknown[], path: string) {
  return (selector?: Selector<T>) =>
    useSuspenseQuery({
      queryKey: key,
      queryFn: () => api.get<T>(path),
      select: (resp) => resp.data,
      ...selector?.query,
    });
}

export const useCurrentUserSuspense = (s?: Selector<CurrentUser>) =>
  useSuspenseQuery({
    queryKey: ["currentUser"],
    queryFn: () => api.get<CurrentUser>("/current-user"),
    select: (r) => r.data,
    ...s?.query,
  });

export const useListSystemsSuspense = (s?: Selector<SystemListOut[]>) =>
  useSuspenseQuery({
    queryKey: ["listSystems"],
    queryFn: () => api.get<SystemListOut[]>("/systems"),
    select: (r) => r.data,
    ...s?.query,
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
  errors: string[];
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

export const useApplyTicket = (
  opts?: Opts<TicketApplyResult, { ticketId: string }>,
) =>
  useMutation({
    mutationFn: async ({ ticketId }) =>
      (await api.post<TicketApplyResult>(`/tickets/${encodeURIComponent(ticketId)}/apply`)).data,
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
  mode?: SyncMode;
  dry_run?: boolean;
}

export interface SyncObjectResult {
  schema_name: string;
  technical_name: string;
  target_table: string;
  status: SyncObjectStatus;
  message?: string | null;
}

export interface SyncRunResult {
  sync_id: string;
  status: SyncStatus;
  objects_total: number;
  objects_synced: number;
  objects_failed: number;
  duration_ms: number;
  target_catalog: string;
  dry_run: boolean;
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
