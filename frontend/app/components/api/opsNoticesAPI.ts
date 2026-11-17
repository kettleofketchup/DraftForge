import { z } from 'zod';
import {
  NoticeCategorySchema,
  NoticeDeliveryStateSchema,
  NoticeSeveritySchema,
  NoticeStateSchema,
  type NoticeCategory,
} from '~/lib/opsnotices/noticeTypes.generated';
import axios from './axios';

export const OpsNoticeUserSchema = z.object({
  id: z.number(),
  username: z.string(),
  nickname: z.string().nullable(),
  avatar: z.string().nullable(),
});
export type OpsNoticeUser = z.infer<typeof OpsNoticeUserSchema>;

export const OpsNoticeSchema = z.object({
  id: z.number(),
  key: z.string(),
  label: z.string(),
  category: NoticeCategorySchema,
  severity: NoticeSeveritySchema,
  state: NoticeStateSchema,
  summary: z.string(),
  event_id: z.number().nullable(),
  event_name: z.string(),
  subject_user: OpsNoticeUserSchema.nullable(),
  actor: OpsNoticeUserSchema.nullable(),
  dedupe_key: z.string(),
  occurrences: z.number(),
  first_seen_at: z.string(),
  last_seen_at: z.string(),
  closed_at: z.string().nullable(),
  close_note: z.string(),
  delivery_state: NoticeDeliveryStateSchema,
  payload: z.record(z.string(), z.unknown()),
});
export type OpsNotice = z.infer<typeof OpsNoticeSchema>;

export interface OpsNoticeListOptions {
  state?: 'open' | 'resolved' | 'all';
  category?: NoticeCategory[];
}

function listUrl(base: string, opts: OpsNoticeListOptions): string {
  const sp = new URLSearchParams();
  if (opts.state) sp.set('state', opts.state);
  if (opts.category?.length) sp.set('category', opts.category.join(','));
  const q = sp.toString();
  return q ? `${base}?${q}` : base;
}

async function fetchList(url: string): Promise<OpsNotice[]> {
  const { data } = await axios.get(url);
  return z.array(OpsNoticeSchema).parse(data);
}

export function fetchEventOpsNotices(
  eventId: number,
  opts: OpsNoticeListOptions,
): Promise<OpsNotice[]> {
  return fetchList(listUrl(`/events/${eventId}/ops-notices/`, opts));
}

export function fetchOrgOpsNotices(
  orgId: number,
  opts: OpsNoticeListOptions,
): Promise<OpsNotice[]> {
  return fetchList(listUrl(`/organizations/${orgId}/ops-notices/`, opts));
}

export async function resolveEventOpsNotice(
  eventId: number,
  noticeId: number,
  reason?: string,
): Promise<OpsNotice> {
  const { data } = await axios.post(
    `/events/${eventId}/ops-notices/${noticeId}/resolve/`,
    reason === undefined ? {} : { reason },
  );
  return OpsNoticeSchema.parse(data);
}
