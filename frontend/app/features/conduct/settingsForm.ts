import {
  ConductSettingsValuesSchema,
  type ConductSettingsField,
  type ConductSettingsForm,
  type ConductSettingsValues,
} from './schemas';

export const CONDUCT_SETTINGS_FIELDS: readonly ConductSettingsField[] =
  ConductSettingsValuesSchema.keyof().options;

export function isConductSettingsField(
  key: string,
): key is ConductSettingsField {
  return (CONDUCT_SETTINGS_FIELDS as readonly string[]).includes(key);
}

export function pickConductFormValues(
  s: ConductSettingsValues,
): ConductSettingsForm {
  return Object.fromEntries(
    CONDUCT_SETTINGS_FIELDS.map((field) => [field, s[field]]),
  ) as ConductSettingsForm;
}

/** DRF `{field: [msg]}` entries that name a settings field. */
export function conductSettingsFieldErrors(
  err: unknown,
): [ConductSettingsField, string][] {
  const data: unknown =
    typeof err === 'object' && err !== null && 'response' in err
      ? (err as { response?: { data?: unknown } }).response?.data
      : undefined;
  if (typeof data !== 'object' || data === null) return [];
  return Object.entries(data).flatMap(
    ([key, value]): [ConductSettingsField, string][] => {
      if (!isConductSettingsField(key)) return [];
      const message = Array.isArray(value) ? value[0] : value;
      return typeof message === 'string' ? [[key, message]] : [];
    },
  );
}
