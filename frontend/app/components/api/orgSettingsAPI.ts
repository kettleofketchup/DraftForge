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
  updated_at: z.string(),
});
export type OrgSettings = z.infer<typeof OrgSettingsSchema>;

export const StaffPlacementFormSchema = z.object({
  staff_override_policy: StaffOverridePolicySchema,
  staff_override_warning_codes: z.array(z.string()),
});
export type StaffPlacementFormValues = z.infer<typeof StaffPlacementFormSchema>;

export const orgSettingsKey = (orgId: number) =>
  ['org-settings', orgId] as const;

export async function getOrgSettings(orgId: number): Promise<OrgSettings> {
  const response = await api.get(`/organizations/${orgId}/settings/`);
  return OrgSettingsSchema.parse(response.data);
}

export async function patchOrgSettings(
  orgId: number,
  body: Partial<StaffPlacementFormValues>,
): Promise<OrgSettings> {
  const response = await api.patch(`/organizations/${orgId}/settings/`, body);
  return OrgSettingsSchema.parse(response.data);
}
