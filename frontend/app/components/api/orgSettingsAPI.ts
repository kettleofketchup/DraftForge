import { z } from 'zod';
import api from './axios';

export const StaffOverridePolicySchema = z.enum(['silent', 'confirm', 'block']);
export type StaffOverridePolicy = z.infer<typeof StaffOverridePolicySchema>;

export const OrgSettingsSchema = z.object({
  organization: z.number(),
  staff_override_policy: StaffOverridePolicySchema,
  staff_override_warning_codes: z.array(z.string()),
  available_warning_codes: z.array(
    z.object({ code: z.string(), label: z.string() }),
  ),
  signup_record_retention_days: z.number().int().nullable(),
  signup_record_min_retention_days: z.number().int(),
  updated_at: z.string(),
});
export type OrgSettings = z.infer<typeof OrgSettingsSchema>;

export const StaffPlacementFormSchema = z.object({
  staff_override_policy: StaffOverridePolicySchema,
  staff_override_warning_codes: z.array(z.string()),
});
export type StaffPlacementFormValues = z.infer<typeof StaffPlacementFormSchema>;

export const SIGNUP_RECORD_MAX_RETENTION_DAYS = 36500;

export const signupRetentionFormSchema = (min: number) =>
  z
    .object({
      retention_mode: z.enum(['forever', 'period']),
      signup_record_retention_days: z.number().int().nullable(),
    })
    .superRefine((value, ctx) => {
      if (value.retention_mode !== 'period') return;
      const days = value.signup_record_retention_days;
      const path = ['signup_record_retention_days'];
      if (days === null) {
        ctx.addIssue({
          code: 'custom',
          path,
          message: 'Enter a number of days.',
        });
      } else if (days < min) {
        ctx.addIssue({ code: 'custom', path, message: `Minimum ${min} days.` });
      } else if (days > SIGNUP_RECORD_MAX_RETENTION_DAYS) {
        ctx.addIssue({
          code: 'custom',
          path,
          message: `Maximum ${SIGNUP_RECORD_MAX_RETENTION_DAYS} days.`,
        });
      }
    });
export type SignupRetentionFormValues = z.infer<
  ReturnType<typeof signupRetentionFormSchema>
>;

export type SignupRetentionPatch = {
  signup_record_retention_days: number | null;
};

export function toRetentionPatch(
  values: SignupRetentionFormValues,
): SignupRetentionPatch {
  return {
    signup_record_retention_days:
      values.retention_mode === 'period'
        ? values.signup_record_retention_days
        : null,
  };
}

export const orgSettingsKey = (orgId: number) =>
  ['org-settings', orgId] as const;

export async function getOrgSettings(orgId: number): Promise<OrgSettings> {
  const response = await api.get(`/organizations/${orgId}/settings/`);
  return OrgSettingsSchema.parse(response.data);
}

export async function patchOrgSettings(
  orgId: number,
  body: Partial<StaffPlacementFormValues & SignupRetentionPatch>,
): Promise<OrgSettings> {
  const response = await api.patch(`/organizations/${orgId}/settings/`, body);
  return OrgSettingsSchema.parse(response.data);
}
