type AxiosLikeError = {
  response?: {
    data?: unknown;
  };
};

/**
 * Best-effort extraction of a user-facing error message from an axios error.
 *
 * Handles three shapes from DRF:
 * - `{ "error": "..." }` (custom error key)
 * - `{ "detail": "..." }` (DRF non-field generic)
 * - `{ "field_name": ["...", "..."] }` (DRF field-level — returns first non-empty
 *   message of first field)
 *
 * Filters out empty strings to avoid surfacing toast.error('').
 */
export function extractApiError(err: unknown): string | undefined {
  const data = (err as AxiosLikeError)?.response?.data;
  if (!data || typeof data !== 'object') return undefined;
  const obj = data as Record<string, unknown>;

  if (typeof obj.error === 'string' && obj.error.length > 0) return obj.error;
  if (typeof obj.detail === 'string' && obj.detail.length > 0) return obj.detail;

  // Field-level error shape: pick the first field's first non-empty message.
  for (const value of Object.values(obj)) {
    if (Array.isArray(value) && value.length > 0 && typeof value[0] === 'string' && value[0].length > 0) {
      return value[0];
    }
    if (typeof value === 'string' && value.length > 0) return value;
  }
  return undefined;
}
