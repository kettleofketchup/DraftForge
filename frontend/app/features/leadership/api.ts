import { z } from 'zod';
import api from '~/components/api/axios';
import {
  EventReviewsSchema,
  LeadershipSettingsSchema,
  MemberLeadershipSchema,
  ModerationReviewSchema,
  MyReviewSchema,
  PendingReviewSchema,
  ReleaseResultSchema,
  ReviewResultSchema,
  TraitsSchema,
  type EventReviews,
  type LeadershipSettings,
  type LeadershipSettingsPatch,
  type MemberLeadership,
  type ModerationReview,
  type MyReview,
  type PendingReview,
  type ReleaseResult,
  type ReviewResult,
  type Scores,
  type Trait,
} from './schemas';

export type TraitPutItem = Pick<Trait, 'key' | 'label' | 'order' | 'active'>;

function base(orgId: number): string {
  return `/organizations/${orgId}/leadership`;
}

function reviewPath(
  orgId: number,
  eventId: number,
  captainOrgUserId: number,
): string {
  return `${base(orgId)}/events/${eventId}/captains/${captainOrgUserId}/review/`;
}

export async function getMemberLeadership(
  orgId: number,
  orgUserPk: number,
): Promise<MemberLeadership> {
  const response = await api.get(`${base(orgId)}/members/${orgUserPk}/`);
  return MemberLeadershipSchema.parse(response.data);
}

export async function getPendingReviews(
  orgId: number,
  eventId: number | null,
): Promise<PendingReview[]> {
  const response = await api.get(`${base(orgId)}/reviews/pending/`, {
    params: eventId === null ? {} : { event_id: eventId },
  });
  return z.array(PendingReviewSchema).parse(response.data);
}

export async function getMyReviews(orgId: number): Promise<MyReview[]> {
  const response = await api.get(`${base(orgId)}/reviews/mine/`);
  return z.array(MyReviewSchema).parse(response.data);
}

export async function putReview(
  orgId: number,
  eventId: number,
  captainOrgUserId: number,
  scores: Scores,
): Promise<ReviewResult> {
  const response = await api.put(reviewPath(orgId, eventId, captainOrgUserId), {
    scores,
  });
  return ReviewResultSchema.parse(response.data);
}

export async function deleteReview(
  orgId: number,
  eventId: number,
  captainOrgUserId: number,
): Promise<void> {
  await api.delete(reviewPath(orgId, eventId, captainOrgUserId));
}

export async function getEventReviews(
  orgId: number,
  eventId: number,
): Promise<EventReviews> {
  const response = await api.get(`${base(orgId)}/events/${eventId}/reviews/`);
  return EventReviewsSchema.parse(response.data);
}

export async function voidReview(
  orgId: number,
  reviewPk: number,
  reason: string,
): Promise<ModerationReview> {
  const response = await api.post(`${base(orgId)}/reviews/${reviewPk}/void/`, {
    reason,
  });
  return ModerationReviewSchema.parse(response.data);
}

export async function unvoidReview(
  orgId: number,
  reviewPk: number,
): Promise<ModerationReview> {
  const response = await api.post(
    `${base(orgId)}/reviews/${reviewPk}/unvoid/`,
    {},
  );
  return ModerationReviewSchema.parse(response.data);
}

export async function releaseResults(
  orgId: number,
  eventId: number,
  captains?: number[],
): Promise<ReleaseResult> {
  const response = await api.post(
    `${base(orgId)}/events/${eventId}/release/`,
    captains === undefined ? {} : { captains },
  );
  return ReleaseResultSchema.parse(response.data);
}

export async function getLeadershipSettings(
  orgId: number,
): Promise<LeadershipSettings> {
  const response = await api.get(`${base(orgId)}/settings/`);
  return LeadershipSettingsSchema.parse(response.data);
}

export async function patchLeadershipSettings(
  orgId: number,
  body: LeadershipSettingsPatch,
): Promise<LeadershipSettings> {
  const response = await api.patch(`${base(orgId)}/settings/`, body);
  return LeadershipSettingsSchema.parse(response.data);
}

export async function getTraits(orgId: number): Promise<Trait[]> {
  const response = await api.get(`${base(orgId)}/traits/`);
  return TraitsSchema.parse(response.data).traits;
}

export async function putTraits(
  orgId: number,
  items: TraitPutItem[],
): Promise<Trait[]> {
  const response = await api.put(`${base(orgId)}/traits/`, { traits: items });
  return TraitsSchema.parse(response.data).traits;
}

export async function deleteTrait(orgId: number, key: string): Promise<void> {
  await api.delete(`${base(orgId)}/traits/${key}/`);
}
