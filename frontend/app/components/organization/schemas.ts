import { z } from 'zod';
import type { UserType } from '~/components/user/types';

export const OrganizationSchema = z.object({
  pk: z.number().optional(),
  name: z.string().min(1, 'Name is required').max(255),
  description: z.string().optional().default(''),
  logo: z.union([z.string().url(), z.literal('')]).optional().default(''),
  discord_link: z.union([z.string().url(), z.literal('')]).optional().default(''),
  rules_template: z.string().optional().default(''),
  owner_id: z.number().nullable().optional(),
  admin_ids: z.array(z.number()).optional(),
  staff_ids: z.array(z.number()).optional(),
  default_league: z.number().nullable().optional(),
  league_count: z.number().optional(),
  tournament_count: z.number().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export const CreateOrganizationSchema = z.object({
  name: z.string().min(1, 'Name is required').max(255),
  description: z.string(),
  logo: z.union([z.string().url(), z.literal('')]),
  discord_link: z.union([z.string().url(), z.literal('')]),
  rules_template: z.string(),
});

export const EditOrganizationSchema = z.object({
  name: z.string().min(1, 'Name is required').max(255),
  description: z.string(),
  logo: z.union([z.string().url(), z.literal('')]),
  discord_link: z.union([z.string().url(), z.literal('')]),
  rules_template: z.string(),
});

// Inferred types from Zod schemas
export type OrganizationType = z.infer<typeof OrganizationSchema> & {
  owner?: UserType | null;
  admins?: UserType[];
  staff?: UserType[];
};
export type CreateOrganizationInput = z.infer<typeof CreateOrganizationSchema>;
export type EditOrganizationInput = z.infer<typeof EditOrganizationSchema>;
export type OrganizationsType = OrganizationType[];
