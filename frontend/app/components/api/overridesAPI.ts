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

export function overrideReasonFormSchema(minLength: number) {
  return z.object({
    reason: z
      .string()
      .trim()
      .min(
        minLength,
        minLength > 1
          ? `Give a reason (at least ${minLength} characters).`
          : 'A reason is required',
      )
      .max(
        OVERRIDE_REASON_MAX_LENGTH,
        `Keep the reason under ${OVERRIDE_REASON_MAX_LENGTH} characters`,
      ),
  });
}

export const OverrideReasonFormSchema = overrideReasonFormSchema(1);
export type OverrideReasonFormValues = z.infer<typeof OverrideReasonFormSchema>;

// First attempt omits `reason` so a caller's own reason field survives `...ack`.
export interface OverrideAcknowledgement {
  acknowledged_codes: string[];
  reason?: string;
}

export const NO_ACKNOWLEDGEMENT: OverrideAcknowledgement = {
  acknowledged_codes: [],
};

export function responseBody(err: unknown, status: number): unknown {
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

export const StaffReasonRequiredSchema = z.object({
  error: z.literal('reason_required'),
});

export function isStaffReasonRequiredError(err: unknown): boolean {
  return StaffReasonRequiredSchema.safeParse(responseBody(err, 400)).success;
}

export function staffReasonFormSchema(required: boolean) {
  return overrideReasonFormSchema(required ? 1 : 0);
}
