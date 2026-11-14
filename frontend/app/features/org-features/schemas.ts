import { z } from 'zod';

export const FEATURE_KEYS = ['contributions', 'promotion'] as const;
export const FeatureKeySchema = z.enum(FEATURE_KEYS);
export type FeatureKey = z.infer<typeof FeatureKeySchema>;

export const OrgFeatureRowSchema = z.object({
  feature: FeatureKeySchema,
  enabled: z.boolean(),
  notes: z.string(),
  enabled_by: z.object({ pk: z.number(), username: z.string() }).nullable(),
  enabled_at: z.string().nullable(),
});
export type OrgFeatureRow = z.infer<typeof OrgFeatureRowSchema>;

export const OrgFeatureRowsSchema = z.array(OrgFeatureRowSchema);

export const OrgFeatureFormSchema = z.object({
  enabled: z.boolean(),
  notes: z.string(),
});
export type OrgFeatureFormValues = z.infer<typeof OrgFeatureFormSchema>;

export interface SetOrgFeaturePayload {
  feature: FeatureKey;
  enabled: boolean;
  notes: string;
}
