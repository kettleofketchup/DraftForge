import type { TraitPutItem } from './api';
import {
  LEADERSHIP_SETTINGS_FIELDS,
  type LeadershipSettings,
  type LeadershipSettingsField,
  type LeadershipSettingsForm,
  type LeadershipSettingsPatch,
  type Trait,
  type TraitForm,
} from './schemas';

export function isLeadershipSettingsField(
  key: string,
): key is LeadershipSettingsField {
  return (LEADERSHIP_SETTINGS_FIELDS as readonly string[]).includes(key);
}

export function pickLeadershipFormValues(
  s: LeadershipSettings,
): LeadershipSettingsForm {
  const values = Object.fromEntries(
    LEADERSHIP_SETTINGS_FIELDS.map((field) => [field, s[field]]),
  ) as Omit<LeadershipSettingsForm, 'points'>;
  return {
    ...values,
    points: Object.fromEntries(s.points.map((p) => [p.kind, p.points])),
  };
}

/** Changed fields only; a point value equal to its default clears the override. */
export function leadershipSettingsPatch(
  values: LeadershipSettingsForm,
  saved: LeadershipSettings,
): LeadershipSettingsPatch {
  const patch: LeadershipSettingsPatch = {};
  for (const field of LEADERSHIP_SETTINGS_FIELDS) {
    if (values[field] !== saved[field]) {
      Object.assign(patch, { [field]: values[field] });
    }
  }
  const points: Record<string, number | null> = {};
  for (const kind of saved.points) {
    const value = values.points[kind.kind];
    if (value === undefined || value === kind.points) continue;
    points[kind.kind] = value === kind.default ? null : value;
  }
  if (Object.keys(points).length > 0) patch.points = points;
  return patch;
}

function responseData(err: unknown): unknown {
  return typeof err === 'object' && err !== null && 'response' in err
    ? (err as { response?: { data?: unknown } }).response?.data
    : undefined;
}

function firstMessage(value: unknown): string | null {
  const message = Array.isArray(value) ? value[0] : value;
  return typeof message === 'string' ? message : null;
}

/** DRF errors mapped onto form paths: `field`, `points.<kind>`, or the max-age `detail`. */
export function leadershipSettingsFieldErrors(
  err: unknown,
): [`points.${string}` | LeadershipSettingsField, string][] {
  const data = responseData(err);
  if (typeof data !== 'object' || data === null) return [];
  return Object.entries(data).flatMap(
    ([key, value]): [
      `points.${string}` | LeadershipSettingsField,
      string,
    ][] => {
      if (key === 'points' && typeof value === 'object' && value !== null) {
        return Object.entries(value).flatMap(
          ([kind, inner]): [`points.${string}`, string][] => {
            const message = firstMessage(inner);
            return message ? [[`points.${kind}`, message]] : [];
          },
        );
      }
      if (key === 'detail') {
        const message = firstMessage(value);
        return message?.startsWith('Max age')
          ? [['max_age_days', message]]
          : [];
      }
      if (!isLeadershipSettingsField(key)) return [];
      const message = firstMessage(value);
      return message ? [[key, message]] : [];
    },
  );
}

/** DRF `{traits: [{label: [msg]}, ...]}` mapped onto `traits.<i>.<field>`. */
export function traitFieldErrors(
  err: unknown,
): [`traits.${number}.${'key' | 'label'}`, string][] {
  const data = responseData(err);
  if (typeof data !== 'object' || data === null || !('traits' in data)) {
    return [];
  }
  const rows = (data as { traits: unknown }).traits;
  if (!Array.isArray(rows)) return [];
  return rows.flatMap(
    (row, index): [`traits.${number}.${'key' | 'label'}`, string][] => {
      if (typeof row !== 'object' || row === null) return [];
      return (['key', 'label'] as const).flatMap(
        (field): [`traits.${number}.${'key' | 'label'}`, string][] => {
          const message = firstMessage((row as Record<string, unknown>)[field]);
          return message ? [[`traits.${index}.${field}`, message]] : [];
        },
      );
    },
  );
}

export function traitFormValues(traits: readonly Trait[]): TraitForm {
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

export function traitPutItems(form: TraitForm): TraitPutItem[] {
  return form.traits.map((t, order) => ({
    key: t.key,
    label: t.label.trim(),
    order,
    active: t.active,
  }));
}

export function slugifyTraitKey(
  label: string,
  taken: ReadonlySet<string>,
  maxLength: number,
): string {
  const base =
    label
      .toLowerCase()
      .normalize('NFKD')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, maxLength) || 'trait';
  if (!taken.has(base)) return base;
  for (let n = 2; ; n += 1) {
    const suffix = `-${n}`;
    const candidate = `${base.slice(0, maxLength - suffix.length)}${suffix}`;
    if (!taken.has(candidate)) return candidate;
  }
}
