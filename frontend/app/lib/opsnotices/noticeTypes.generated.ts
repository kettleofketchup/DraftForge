// GENERATED FILE - DO NOT EDIT.
// Source: backend/*/ops_notices.py via backend/opsnotices/export_schema.py
// Regenerate with: just py::gen-notice-types
import { z } from 'zod';

export const NOTICE_CATEGORIES = ['log', 'urgent', 'task'] as const;
export const NoticeCategorySchema = z.enum(NOTICE_CATEGORIES);
export type NoticeCategory = z.infer<typeof NoticeCategorySchema>;

export const NOTICE_SEVERITIES = ['info', 'warning', 'critical'] as const;
export const NoticeSeveritySchema = z.enum(NOTICE_SEVERITIES);
export type NoticeSeverity = z.infer<typeof NoticeSeveritySchema>;

export const NOTICE_STATES = ['open', 'resolved'] as const;
export const NoticeStateSchema = z.enum(NOTICE_STATES);
export type NoticeState = z.infer<typeof NoticeStateSchema>;

export const NOTICE_DELIVERY_STATES = [
  'pending',
  'sent',
  'partial',
  'failed',
  'unrouted',
] as const;
export const NoticeDeliveryStateSchema = z.enum(NOTICE_DELIVERY_STATES);
export type NoticeDeliveryState = z.infer<typeof NoticeDeliveryStateSchema>;

export const NOTICE_KEYS = [] as const satisfies readonly string[];

export const NoticeTypeMetaSchema = z.object({
  key: z.string(),
  label: z.string().min(1),
  description: z.string().min(1),
  category: NoticeCategorySchema,
  defaultSeverity: NoticeSeveritySchema,
  autoResolves: z.boolean(),
  dedupes: z.boolean(),
});
export type NoticeTypeMeta = z.infer<typeof NoticeTypeMetaSchema>;

export const NOTICE_TYPES: readonly NoticeTypeMeta[] = [];
