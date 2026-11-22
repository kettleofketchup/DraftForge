import type { TraitPutItem } from './api';
import { TRAIT_KEY_MAX_LENGTH, type Trait, type TraitForm } from './schemas';

export type TraitFieldPath = 'traits' | `traits.${number}.${'key' | 'label'}`;

export function slugifyTraitKey(
  label: string,
  taken: ReadonlySet<string>,
): string {
  const base =
    label
      .toLowerCase()
      .normalize('NFKD')
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .slice(0, TRAIT_KEY_MAX_LENGTH)
      .replace(/_+$/, '') || 'trait';
  if (!taken.has(base)) return base;
  for (let n = 2; ; n += 1) {
    const suffix = `_${n}`;
    const stem = base
      .slice(0, TRAIT_KEY_MAX_LENGTH - suffix.length)
      .replace(/_+$/, '');
    const candidate = `${stem}${suffix}`;
    if (!taken.has(candidate)) return candidate;
  }
}

export function toTraitForm(traits: readonly Trait[]): TraitForm {
  return {
    traits: [...traits]
      .sort((a, b) => a.order - b.order)
      .map((t) => ({
        key: t.key,
        label: t.label,
        active: t.active,
        saved: true,
      })),
  };
}

export function toTraitPut(values: TraitForm): TraitPutItem[] {
  return values.traits.map((t, order) => ({
    key: t.key,
    label: t.label.trim(),
    order,
    active: t.active,
  }));
}

function firstMessage(value: unknown): string | null {
  const message = Array.isArray(value) ? value[0] : value;
  return typeof message === 'string' ? message : null;
}

/** DRF `{traits: [{label: [msg]}, ...]}` onto `traits.<i>.<field>`; `{detail}` onto the list root. */
export function traitFieldErrors(err: unknown): [TraitFieldPath, string][] {
  const data =
    typeof err === 'object' && err !== null && 'response' in err
      ? (err as { response?: { data?: unknown } }).response?.data
      : undefined;
  if (typeof data !== 'object' || data === null) return [];
  const { traits: rows, detail } = data as Record<string, unknown>;
  const errors: [TraitFieldPath, string][] = [];
  if (Array.isArray(rows)) {
    rows.forEach((row, index) => {
      if (typeof row !== 'object' || row === null) return;
      for (const field of ['key', 'label'] as const) {
        const message = firstMessage((row as Record<string, unknown>)[field]);
        if (message) errors.push([`traits.${index}.${field}`, message]);
      }
    });
  } else {
    const message = firstMessage(rows);
    if (message) errors.push(['traits', message]);
  }
  const message = firstMessage(detail);
  if (message) errors.push(['traits', message]);
  return errors;
}
