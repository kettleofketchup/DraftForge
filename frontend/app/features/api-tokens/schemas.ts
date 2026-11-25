import { z } from 'zod';

export const TOKEN_NAME_MAX_LENGTH = 64;
export const PER_MINUTE_MAX = 10_000;
export const PER_DAY_MAX = 1_000_000;
export const USAGE_DAYS = 30;

// Hand-written from backend/org/api_tokens/views.py (_user_ref, _token_row).
export const ApiUserRefSchema = z.object({
  pk: z.number(),
  username: z.string().nullable(),
});
export type ApiUserRef = z.infer<typeof ApiUserRefSchema>;

// Hand-written from backend/org/api_tokens/operations.py (Operation).
export const TOKEN_OPERATION_VALUES = [
  'mmr:read',
  'mmr:write',
  'promotion:read',
  'promotion:import',
  'contributions:read',
] as const;
export type TokenOperation = (typeof TOKEN_OPERATION_VALUES)[number];

/** The org feature each operation needs, as in operations._ENTITLEMENTS. */
export type TokenFeature = 'mmr_sync' | 'promotion' | 'contributions';

export interface TokenOperationInfo {
  value: TokenOperation;
  label: string;
  feature: TokenFeature;
}

export const TOKEN_OPERATIONS: readonly TokenOperationInfo[] = [
  { value: 'mmr:read', label: 'Read member MMRs', feature: 'mmr_sync' },
  { value: 'mmr:write', label: 'Update member MMRs', feature: 'mmr_sync' },
  {
    value: 'promotion:read',
    label: 'Read promotion recipients',
    feature: 'promotion',
  },
  {
    value: 'promotion:import',
    label: 'Import external contact history',
    feature: 'promotion',
  },
  {
    value: 'contributions:read',
    label: 'Read contribution totals',
    feature: 'contributions',
  },
];

export const TOKEN_FEATURE_LABELS: Record<TokenFeature, string> = {
  mmr_sync: 'MMR sync API',
  promotion: 'Promotion',
  contributions: 'Contributions',
};

/** What the backend grants a token issued without operations, and every token that predates grants. */
export const DEFAULT_TOKEN_OPERATIONS: readonly TokenOperation[] = [
  'mmr:read',
  'mmr:write',
];

export function operationLabel(value: string): string {
  return TOKEN_OPERATIONS.find((op) => op.value === value)?.label ?? value;
}

export const ApiTokenSchema = z.object({
  id: z.number(),
  name: z.string(),
  prefix: z.string(),
  user: ApiUserRefSchema.nullable(),
  created_at: z.string(),
  last_used_at: z.string().nullable(),
  revoked_at: z.string().nullable(),
  revoked_by: ApiUserRefSchema.nullable(),
  // Strings, not the enum, so a grant added on the backend still lists.
  operations: z
    .array(z.string())
    .optional()
    .transform((ops) => ops ?? [...DEFAULT_TOKEN_OPERATIONS]),
});
export type ApiToken = z.infer<typeof ApiTokenSchema>;

export const ApiTokensSchema = z.array(ApiTokenSchema);

export const CreatedApiTokenSchema = ApiTokenSchema.extend({
  token: z.string(),
});
export type CreatedApiToken = z.infer<typeof CreatedApiTokenSchema>;

export const ApiLimitsSchema = z.object({
  per_minute: z.number().int(),
  per_day: z.number().int(),
});
export type ApiLimits = z.infer<typeof ApiLimitsSchema>;

export const ApiUsageDaySchema = z.object({
  date: z.string(),
  requests: z.number(),
  throttled: z.number(),
});
export type ApiUsageDay = z.infer<typeof ApiUsageDaySchema>;

export const ApiUsageUserSchema = z.object({
  user: ApiUserRefSchema,
  requests: z.number(),
  throttled: z.number(),
  days: z.array(ApiUsageDaySchema),
});
export type ApiUsageUser = z.infer<typeof ApiUsageUserSchema>;

// Hand-written from backend/org/api_tokens/views.py (org_api_usage).
export const ApiUsageSchema = z.object({
  since: z.string(),
  days: z.number(),
  limits: ApiLimitsSchema,
  users: z.array(ApiUsageUserSchema),
});
export type ApiUsage = z.infer<typeof ApiUsageSchema>;

export const CreateTokenFormSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, 'Name is required')
    .max(TOKEN_NAME_MAX_LENGTH, `At most ${TOKEN_NAME_MAX_LENGTH} characters`),
  operations: z
    .array(z.enum(TOKEN_OPERATION_VALUES))
    .min(1, 'Pick at least one operation'),
});
export type CreateTokenForm = z.infer<typeof CreateTokenFormSchema>;

export interface CreateApiTokenInput {
  name: string;
  operations: readonly string[];
}

export const ApiLimitsFormSchema = z.object({
  per_minute: z
    .number({ error: 'Enter a number' })
    .int('Whole numbers only')
    .min(1, 'At least 1')
    .max(PER_MINUTE_MAX, `At most ${PER_MINUTE_MAX.toLocaleString()}`),
  per_day: z
    .number({ error: 'Enter a number' })
    .int('Whole numbers only')
    .min(1, 'At least 1')
    .max(PER_DAY_MAX, `At most ${PER_DAY_MAX.toLocaleString()}`),
});
export type ApiLimitsForm = z.infer<typeof ApiLimitsFormSchema>;

export const LIMIT_FIELDS = ['per_minute', 'per_day'] as const;
export type LimitField = (typeof LIMIT_FIELDS)[number];

export function isLimitField(field: string): field is LimitField {
  return (LIMIT_FIELDS as readonly string[]).includes(field);
}
