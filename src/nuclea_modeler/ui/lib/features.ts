/**
 * Feature flag helper for the frontend.
 *
 * Reads /api/features once on app mount via TanStack Query and exposes a
 * tiny API to gate UI elements.
 *
 * Usage:
 *   const { isEnabled } = useFeatures();
 *   if (isEnabled("der_minimap")) return <Minimap />;
 *
 * Unknown flag names always return false — safer than crashing on a typo.
 */
import { useGetFeaturesSuspense, type FeaturesOut } from "@/lib/api";
import selector from "@/lib/selector";

export type FeatureFlag =
  | "global_search_v2"
  | "embarcadero_v2"
  | "ddl_import_dry_run"
  | "der_minimap"
  | "der_auto_layout_v2"
  | "versions_signed"
  | "sync_column_lineage"
  | "structured_logs";

export interface FeatureApi {
  features: Record<string, boolean>;
  isEnabled: (flag: FeatureFlag) => boolean;
}

/**
 * Suspense-friendly feature-flag hook. The TanStack Router suspense
 * pattern in this codebase means callers must be wrapped in a <Suspense>
 * boundary — which every routed page already does.
 */
export function useFeatures(): FeatureApi {
  const { data } = useGetFeaturesSuspense(selector()) as { data: FeaturesOut };
  const features = (data?.features ?? {}) as Record<string, boolean>;
  return {
    features,
    isEnabled: (flag) => Boolean(features[flag]),
  };
}

/**
 * Non-suspense escape hatch for places where we can't (or don't want to)
 * suspend — e.g. inside an event handler. Returns false on miss instead of
 * throwing. Prefer `useFeatures` whenever possible.
 */
export function isFeatureEnabledFromCache(
  cache: Record<string, boolean> | undefined,
  flag: FeatureFlag,
): boolean {
  return Boolean(cache?.[flag]);
}
