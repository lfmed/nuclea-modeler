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
