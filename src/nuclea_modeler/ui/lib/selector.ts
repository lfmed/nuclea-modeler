/**
 * Selector helper — kept for backwards compat with apx/orval's hook signature.
 *
 * Our hand-written lib/api.ts already unwraps Axios's `{ data }` envelope, so
 * passing `selector()` to a hook just means "default options, no extra
 * mapping". We keep the call shape (`useXSuspense(selector())`) so route files
 * don't need to change.
 */
export const selector = () => ({}) as { query?: { staleTime?: number } };

export default selector;
