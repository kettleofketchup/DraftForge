import { isAxiosError } from 'axios';
import { z } from 'zod';

// backend/events/overrides.py (rendered by app/exception_handler.py)
export const OverrideViolationSchema = z.object({
  code: z.string(),
  rule: z.string(),
  category: z.enum(['seating', 'eligibility', 'team']),
  message: z.string(),
  blocking: z.boolean(),
  params: z.record(z.string(), z.unknown()),
});
export type OverrideViolation = z.infer<typeof OverrideViolationSchema>;

export const OverrideRequiredSchema = z.object({
  code: z.literal('override_required'),
  blocked: z.boolean(),
  violations: z.array(OverrideViolationSchema),
});
export type OverrideRequired = z.infer<typeof OverrideRequiredSchema>;

export const OverrideReasonRequiredSchema = z.object({
  code: z.literal('override_reason_required'),
});

export const OVERRIDE_REASON_MAX_LENGTH = 500;

export const OverrideReasonFormSchema = z.object({
  reason: z
    .string()
    .trim()
    .min(1, 'A reason is required')
    .max(
      OVERRIDE_REASON_MAX_LENGTH,
      `Keep the reason under ${OVERRIDE_REASON_MAX_LENGTH} characters`,
    ),
});
export type OverrideReasonFormValues = z.infer<typeof OverrideReasonFormSchema>;

export interface OverrideAcknowledgement {
  acknowledged_codes: string[];
  reason: string;
}

export const NO_ACKNOWLEDGEMENT: OverrideAcknowledgement = {
  acknowledged_codes: [],
  reason: '',
};

function responseBody(err: unknown, status: number): unknown {
  if (!isAxiosError(err) || err.response?.status !== status) return undefined;
  return err.response.data;
}

export function getOverrideRequired(err: unknown): OverrideRequired | null {
  const parsed = OverrideRequiredSchema.safeParse(responseBody(err, 409));
  return parsed.success ? parsed.data : null;
}

export function isOverrideRequiredError(err: unknown): boolean {
  return getOverrideRequired(err) !== null;
}

export function isOverrideReasonRequiredError(err: unknown): boolean {
  return OverrideReasonRequiredSchema.safeParse(responseBody(err, 400)).success;
}
