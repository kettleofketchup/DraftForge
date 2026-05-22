import { ChevronDown } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
import type { UserClassType, UserType } from '~/components/user';
import { brandErrorBg, brandErrorCard } from '~/components/ui/buttons';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '~/components/ui/collapsible';
import UserEditModal from '~/components/user/userCard/editModal';
import type { EditUserScope } from '~/components/user/userCard/editUserSchema';
import { getLogger } from '~/lib/logger';
import { cn } from '~/lib/utils';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import type { UserEntry } from '~/store/userCacheTypes';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';
const log = getLogger('hasErrors');

/**
 * Derive the EditUserModal scope for the tournament-edit panel.
 * Order: league > org > global. Falls back to global only when neither
 * is loaded — callers should ensure currentOrg is populated before render
 * (TournamentDetailPage calls getOrganization in a useEffect on mount).
 */
export function deriveEditScope({
  league,
  currentOrg,
}: {
  league: LeagueType | null;
  currentOrg: OrganizationType | null;
}): EditUserScope {
  if (league) return { kind: 'league', league };
  if (currentOrg) return { kind: 'org', organization: currentOrg };
  return { kind: 'global' };
}

interface UserIssue {
  user: UserClassType;
  issues: string[];
}

/** Convert a UserEntry to a UserType-like object with org-scoped fields flattened. */
function toUserType(entry: UserEntry, orgId?: number): UserClassType {
  const orgData = orgId ? entry.orgData[orgId] : undefined;
  return {
    ...entry,
    orgUserPk: orgData?.id,
    mmr: orgData?.mmr,
  } as unknown as UserClassType;
}

function hasNoPositions(user: UserEntry): boolean {
  const positions = user.positions;
  if (!positions) return true;
  const totalPreference =
    (positions.carry || 0) +
    (positions.mid || 0) +
    (positions.offlane || 0) +
    (positions.soft_support || 0) +
    (positions.hard_support || 0);
  return totalPreference === 0;
}

export const hasErrors = () => {
  const tournament = useUserStore((state) => state.tournament);
  const entities = useUserCacheStore((state) => state.entities);
  const league = useLeagueStore((state) => state.currentLeague);
  // Default closed for SSR (mobile-first) so hydration matches; expand once
  // on mount when the viewport is md+ so desktop admins see the issues
  // immediately. After that the user controls open/close manually.
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (typeof window !== 'undefined' && window.matchMedia('(min-width: 768px)').matches) {
      setOpen(true);
    }
  }, []);

  const orgId = tournament?.organization_pk ?? undefined;

  const currentOrg = useOrgStore((state) => state.currentOrg);

  const editScope = useMemo<EditUserScope>(
    () => deriveEditScope({ league, currentOrg }),
    [league?.pk, currentOrg?.pk],
  );

  // Resolve users from entity cache — the single source of truth
  const usersWithIssues = useMemo(() => {
    if (!tournament?.users) return [];

    const issues: UserIssue[] = [];

    for (const userRef of tournament.users) {
      const pk = typeof userRef === 'number' ? userRef : (userRef as UserType)?.pk;
      if (!pk) continue;

      const cached = entities[pk];
      if (!cached) continue;

      const userIssues: string[] = [];

      // Check org-scoped MMR from the entity cache
      const mmr = orgId ? cached.orgData[orgId]?.mmr : undefined;
      if (!mmr) {
        userIssues.push('No MMR');
      }
      if (!cached.steam_account_id) {
        userIssues.push('No Friend ID');
      }
      if (hasNoPositions(cached)) {
        userIssues.push('No positions');
      }

      if (userIssues.length > 0) {
        issues.push({ user: toUserType(cached, orgId), issues: userIssues });
      }
    }

    log.debug('Users with issues:', issues.length, issues);
    return issues;
  }, [tournament?.users, entities, orgId]);

  if (usersWithIssues.length === 0) return null;

  const count = usersWithIssues.length;
  const label = `${count} player${count !== 1 ? 's have' : ' has'} incomplete profiles`;

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className={cn('rounded-lg shadow-md w-full mb-4', brandErrorBg)}
      data-testid="incomplete-profiles-banner"
    >
      <CollapsibleTrigger
        className="flex items-center justify-between gap-3 w-full p-3 sm:p-4 text-red-500 font-bold text-left cursor-pointer min-h-11"
        data-testid="incomplete-profiles-toggle"
        aria-label={open ? `Hide ${label}` : `Show ${label}`}
      >
        <span className="flex items-center gap-2 min-w-0">
          <span className="text-lg shrink-0" aria-hidden>⚠️</span>
          <span className="truncate">{label}</span>
        </span>
        <ChevronDown
          className={cn(
            'size-5 shrink-0 transition-transform duration-200',
            open && 'rotate-180',
          )}
          aria-hidden
        />
      </CollapsibleTrigger>
      <CollapsibleContent
        className="overflow-hidden"
        data-testid="incomplete-profiles-list"
      >
        <div className="grid grid-cols-1 min-[420px]:grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 p-3 sm:p-4 pt-0 sm:pt-0">
          {usersWithIssues.map(({ user, issues }) => (
            <div className={cn('p-3 rounded-lg', brandErrorCard)} key={user.pk}>
              <div className="text-white text-center underline underline-offset-2 font-bold mb-2 break-words">
                {user.nickname || user.username}
              </div>
              <div className="flex flex-col gap-1 text-center text-sm text-red-100">
                {issues.map((issue) => (
                  <span key={issue}>{issue}</span>
                ))}
              </div>
              <div className="flex justify-center mt-3">
                <UserEditModal
                  user={user}
                  scope={editScope}
                  key={`UserEditModal-${user.pk}`}
                />
              </div>
            </div>
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
};
