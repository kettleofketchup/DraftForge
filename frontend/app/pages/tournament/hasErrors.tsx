import { ChevronDown } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useShallow } from 'zustand/react/shallow';
import {
  GAME_LABEL,
  GAME_TYPE,
  toGameType,
  type GameTypeValue,
} from '~/components/game/constants';
import { brandErrorBg, brandErrorCard } from '~/components/ui/buttons';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '~/components/ui/collapsible';
import type { UserClassType, UserType } from '~/components/user';
import { DisplayName } from '~/components/user/avatar';
import UserEditModal from '~/components/user/userCard/editModal';
import {
  resolveEditScope,
  resolveOrgUserLink,
  type EditUserScope,
} from '~/components/user/userCard/editUserSchema';
import { getLogger } from '~/lib/logger';
import { cn } from '~/lib/utils';
import { useLeagueStore } from '~/store/leagueStore';
import { useOrgStore } from '~/store/orgStore';
import { selectOrgMmr } from '~/store/selectOrgMmr';
import { selectPositions } from '~/store/selectPositions';
import { useUserCacheStore } from '~/store/userCacheStore';
import type { PositionsType, UserEntry } from '~/store/userCacheTypes';
import { useUserStore } from '~/store/userStore';
import { tournamentEditContext } from './tournamentEditContext';
const log = getLogger('hasErrors');

interface UserIssue {
  user: UserClassType;
  scope: EditUserScope;
  issues: string[];
}

/** Convert a UserEntry to a UserType-like object with org-scoped fields flattened. */
function toUserType(
  entry: UserEntry,
  gameType: GameTypeValue,
  orgId?: number,
  leagueId?: number,
): UserClassType {
  return {
    ...entry,
    orgUserPk: resolveOrgUserLink(entry, { organizationId: orgId, leagueId }),
    mmr: selectOrgMmr(entry, orgId, gameType),
    mmr_game_type: gameType,
  } as unknown as UserClassType;
}

function hasNoPositions(positions: PositionsType | undefined): boolean {
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
  const gameType = toGameType(tournament?.game_type);
  const entities = useUserCacheStore((state) => state.entities);
  const league = useLeagueStore((state) => state.currentLeague);
  // SSR-safe default closed; md+ viewports auto-expand on mount to avoid hydration mismatch.
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (
      typeof window !== 'undefined' &&
      window.matchMedia('(min-width: 768px)').matches
    ) {
      setOpen(true);
    }
  }, []);

  const { organizationId: orgId, leagueId } = tournamentEditContext(tournament);

  const currentOrg = useOrgStore((state) => state.currentOrg);

  // Route positions through the gameType-aware selector. Explicit GAME_TYPE.DOTA2
  // because the tournament route never sets currentGameType — incomplete-profile
  // detection is inherently Dota, so the ambient (null) gameType would flag every
  // player as "No positions". Flat record so useShallow compares values by
  // Object.is (selectPositions returns the stored reference).
  const tournamentUserPks = (tournament?.users ?? [])
    .map((u) => (typeof u === 'number' ? u : (u as UserType)?.pk))
    .filter((pk): pk is number => pk != null);
  const positionsByPk = useUserCacheStore(
    useShallow((s) => {
      const rec: Record<number, PositionsType | undefined> = {};
      for (const pk of tournamentUserPks) {
        rec[pk] = selectPositions(s, pk, GAME_TYPE.DOTA2);
      }
      return rec;
    }),
  );

  // Resolve users from entity cache — the single source of truth
  const usersWithIssues = useMemo(() => {
    if (!tournament?.users) return [];

    const issues: UserIssue[] = [];

    for (const userRef of tournament.users) {
      const pk =
        typeof userRef === 'number' ? userRef : (userRef as UserType)?.pk;
      if (!pk) continue;

      const cached = entities[pk];
      if (!cached) continue;

      const userIssues: string[] = [];

      // Check org-scoped MMR from the entity cache
      const mmr = selectOrgMmr(cached, orgId, gameType);
      if (!mmr) {
        userIssues.push(`No ${GAME_LABEL[gameType]} MMR`);
      }
      if (!cached.steam_account_id) {
        userIssues.push('No Friend ID');
      }
      if (hasNoPositions(positionsByPk[pk])) {
        userIssues.push('No positions');
      }

      if (userIssues.length > 0) {
        const user = toUserType(cached, gameType, orgId, leagueId);
        const scope = resolveEditScope(user, {
          organizationId: orgId,
          leagueId,
          currentOrg,
          currentLeague: league,
          gameType,
        });
        issues.push({ user, scope, issues: userIssues });
      }
    }

    log.debug('Users with issues:', issues.length, issues);
    return issues;
  }, [
    tournament?.users,
    tournament?.game_type,
    gameType,
    entities,
    orgId,
    leagueId,
    currentOrg,
    league,
    positionsByPk,
  ]);

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
        className="grid grid-cols-[auto_1fr_auto] items-center gap-3 w-full p-3 sm:p-4 text-error font-bold cursor-pointer min-h-11"
        data-testid="incomplete-profiles-toggle"
        aria-label={open ? `Hide ${label}` : `Show ${label}`}
      >
        <span className="text-lg" aria-hidden>
          ⚠️
        </span>
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
          {usersWithIssues.map(({ user, scope, issues }) => (
            <div
              className={cn(
                'flex flex-col p-3 rounded-lg h-full',
                brandErrorCard,
              )}
              key={user.pk}
            >
              <div className="text-white text-center underline underline-offset-2 font-bold mb-2 break-words">
                {DisplayName(user)}
              </div>
              <div className="flex flex-col gap-1 text-center text-sm text-error-foreground">
                {issues.map((issue) => (
                  <span key={issue}>{issue}</span>
                ))}
              </div>
              <div className="flex justify-center mt-auto pt-3">
                <UserEditModal
                  user={user}
                  scope={scope}
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
