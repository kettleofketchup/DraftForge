import { ChevronDown } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { UserClassType, UserType } from '~/components/user';
import { brandErrorBg, brandErrorCard } from '~/components/ui/buttons';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '~/components/ui/collapsible';
import UserEditModal from '~/components/user/userCard/editModal';
import { resolveEditScope } from '~/components/user/userCard/editUserSchema';
import { getLogger } from '~/lib/logger';
import { cn } from '~/lib/utils';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import type { UserEntry } from '~/store/userCacheTypes';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';
const log = getLogger('hasErrors');

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
  // SSR-safe default closed; md+ viewports auto-expand on mount to avoid hydration mismatch.
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (typeof window !== 'undefined' && window.matchMedia('(min-width: 768px)').matches) {
      setOpen(true);
    }
  }, []);

  const orgId = tournament?.organization_pk ?? undefined;

  const currentOrg = useOrgStore((state) => state.currentOrg);

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
        className="grid grid-cols-[auto_1fr_auto] items-center gap-3 w-full p-3 sm:p-4 text-red-500 font-bold cursor-pointer min-h-11"
        data-testid="incomplete-profiles-toggle"
        aria-label={open ? `Hide ${label}` : `Show ${label}`}
      >
        <span className="text-lg" aria-hidden>⚠️</span>
        <span className="truncate text-center">{label}</span>
        <ChevronDown
          className={cn(
            'size-5 transition-transform duration-200',
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
            <div
              className={cn('flex flex-col p-3 rounded-lg h-full', brandErrorCard)}
              key={user.pk}
            >
              <div className="text-white text-center underline underline-offset-2 font-bold mb-2 break-words">
                {user.nickname || user.username}
              </div>
              <div className="flex flex-col gap-1 text-center text-sm text-red-100">
                {issues.map((issue) => (
                  <span key={issue}>{issue}</span>
                ))}
              </div>
              <div className="flex justify-center mt-auto pt-3">
                <UserEditModal
                  user={user}
                  scope={resolveEditScope(user, {
                    organizationId: orgId,
                    leagueId: league?.pk,
                    currentOrg,
                    currentLeague: league,
                  })}
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
