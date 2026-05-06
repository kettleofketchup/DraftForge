import type { SignupInputPatch } from './schema';
import type { DotaProfileData } from '~/components/user';

/**
 * Diffs form values against the profile and returns only changed fields.
 * Used so the request body to /signup/ is a minimal patch (matches backend's
 * "fields not in patch are not touched" contract).
 *
 * Order-dependent for arrays (positions) — caller is expected to emit sorted
 * positions; the form does this naturally because ToggleGroup preserves
 * insertion order.
 */
export function toPatch(
  values: SignupInputPatch,
  profile: DotaProfileData | null | undefined,
): Partial<SignupInputPatch> {
  if (!profile) return values;

  const patch: Record<string, unknown> = {};
  const v = values as Record<string, unknown>;
  const p = profile as unknown as Record<string, unknown>;

  for (const key of Object.keys(v)) {
    if (v[key] === undefined) continue;
    if (JSON.stringify(v[key]) !== JSON.stringify(p[key])) {
      patch[key] = v[key];
    }
  }
  return patch as Partial<SignupInputPatch>;
}
