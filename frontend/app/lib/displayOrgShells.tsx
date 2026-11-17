import type { ReactNode } from 'react';
import { useParams } from 'react-router';

import { DisplayOrgProvider } from '~/lib/displayOrgContext';
import { useHeroDraftStore } from '~/store/heroDraftStore';
import { useUserStore } from '~/store/userStore';

type Children = { children: ReactNode };

export function TournamentDisplayOrg({
  tournament,
  children,
}: Children & {
  tournament: { organization_pk?: number | null } | null | undefined;
}) {
  return (
    <DisplayOrgProvider orgId={tournament?.organization_pk}>
      {children}
    </DisplayOrgProvider>
  );
}

export function LeagueDisplayOrg({
  league,
  children,
}: Children & {
  league:
    | {
        organization?: { pk: number } | null;
        organization_id?: number | null;
      }
    | null
    | undefined;
}) {
  return (
    <DisplayOrgProvider
      orgId={league?.organization?.pk ?? league?.organization_id}
    >
      {children}
    </DisplayOrgProvider>
  );
}

export function OrgParamDisplayOrg({ children }: Children) {
  const { organizationId } = useParams();
  const pk = organizationId ? parseInt(organizationId, 10) : NaN;
  return (
    <DisplayOrgProvider orgId={Number.isNaN(pk) ? null : pk}>
      {children}
    </DisplayOrgProvider>
  );
}

export function HeroDraftDisplayOrg({
  draftId,
  children,
}: Children & { draftId: number | null }) {
  const orgId = useHeroDraftStore((s) =>
    s.draft && s.draft.id === draftId
      ? (s.draft.organization_pk ?? null)
      : null,
  );
  return <DisplayOrgProvider orgId={orgId}>{children}</DisplayOrgProvider>;
}

export function CurrentTournamentDisplayOrg({ children }: Children) {
  const orgId = useUserStore((s) => s.tournament?.organization_pk ?? null);
  return <DisplayOrgProvider orgId={orgId}>{children}</DisplayOrgProvider>;
}
