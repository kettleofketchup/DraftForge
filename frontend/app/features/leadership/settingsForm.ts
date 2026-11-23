import { drfErrorData, firstMessage } from './errors';
import {
  LEADERSHIP_SETTINGS_FIELDS,
  type LeadershipSettings,
  type LeadershipSettingsField,
  type LeadershipSettingsForm,
  type LeadershipSettingsPatch,
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

/** DRF errors mapped onto form paths: `field` or `points.<kind>`; anything else is left to the caller. */
export function leadershipSettingsFieldErrors(
  err: unknown,
): [`points.${string}` | LeadershipSettingsField, string][] {
  const data = drfErrorData(err);
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
      if (!isLeadershipSettingsField(key)) return [];
      const message = firstMessage(value);
      return message ? [[key, message]] : [];
    },
  );
}
