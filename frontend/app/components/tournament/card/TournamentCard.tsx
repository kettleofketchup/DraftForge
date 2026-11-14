import React, { memo, useState } from 'react';
import type {
  LeagueMinimal,
  TournamentBucket,
  TournamentType,
} from '~/components/tournament/types';
import {
  displayState,
  isTournamentLive,
  leagueId,
  leagueInfo,
} from '~/components/tournament/tournamentBuckets';
import { cn } from '~/lib/utils';

import {
  Building2,
  Calendar,
  Clock,
  Crown,
  Eye,
  Swords,
  Trophy,
  UserPlus,
  Users,
} from 'lucide-react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router';
import { useUserStore } from '~/store/userStore';
import { Badge } from '../../ui/badge';
import { EditIconButton, PrimaryButton } from '../../ui/buttons';
import {
  CardAction,
  CardDescription,
  CardHeader,
  CardTitle,
} from '../../ui/card';
import { Item, ItemContent, ItemMedia, ItemTitle } from '../../ui/item';
import { SimpleAvatar } from '../../ui/simple-avatar';
import {
  STATE_TILE_CLASSES,
  TOURNAMENT_CARD_CELL,
  TOURNAMENT_CARD_SURFACE,
  stateTone,
} from './cardStyles';
import { TournamentRemoveButton } from './deleteButton';
import { TournamentEditModal } from './TournamentEditModal';
interface Props {
  tournament: TournamentType;
  /** Animation delay index for staggered loading */
  animationIndex?: number;
  bucket?: TournamentBucket;
  /** Show a "Signups open" badge (listed for its open signups, not membership). */
  signupsOpen?: boolean;
}

/** className that lets the cell trim its content with native CSS ellipsis. */
const CELL_TRUNCATE = 'block w-full overflow-hidden text-ellipsis whitespace-nowrap';
/** className for fixed-vocabulary values (date, time, style, state): wrap, never clip. */
const CELL_WRAP = 'block w-full break-words';

const LeagueCell = memo(function LeagueCell({
  league,
}: {
  league: LeagueMinimal | number | null | undefined;
}) {
  const hasLeague = league != null;
  const leagueName = !hasLeague
    ? 'No league'
    : typeof league === 'number'
      ? `League #${league}`
      : league.name || 'Unknown League';

  return (
    <Item size="sm" variant="muted" className="!p-1.5 min-w-0" data-testid="tournament-cell-league">
      <ItemMedia
        variant="icon"
        className={cn('!size-6', hasLeague ? 'bg-primary/20 border-primary/30' : 'bg-muted border-border')}
      >
        <Trophy className={cn('size-3', hasLeague ? 'text-primary' : 'text-muted-foreground')} aria-hidden />
      </ItemMedia>
      <ItemContent className="!gap-0 min-w-0">
        <ItemTitle className="!text-xs text-muted-foreground">League</ItemTitle>
        <span
          className={cn('text-sm font-medium', !hasLeague && 'text-muted-foreground', CELL_TRUNCATE)}
          title={leagueName}
        >
          {leagueName}
        </span>
      </ItemContent>
    </Item>
  );
});

const OrgCell = memo(function OrgCell({ league }: { league: LeagueMinimal | null }) {
  const [logoFailed, setLogoFailed] = useState(false);
  const orgName = league?.organization_name || null;
  const logo = league?.organization_logo || null;
  const hasOrg = !!orgName;

  let media: React.ReactNode;
  if (hasOrg && logo && !logoFailed) {
    media = (
      <SimpleAvatar
        src={logo}
        alt=""
        fallback=""
        className="size-full rounded-sm"
        onError={() => setLogoFailed(true)}
      />
    );
  } else if (hasOrg) {
    media = (
      <div
        data-testid="tournament-card-org-fallback"
        className="flex size-full items-center justify-center rounded-sm border border-primary/30 bg-primary/20"
      >
        <Building2 className="size-3.5 text-primary" aria-hidden />
      </div>
    );
  } else {
    media = (
      <div
        data-testid="tournament-card-org-fallback"
        className="flex size-full items-center justify-center rounded-sm border border-border bg-muted"
      >
        <Building2 className="size-3.5 text-muted-foreground" aria-hidden />
      </div>
    );
  }

  const label = orgName ?? 'No organization';

  return (
    <div className="flex min-w-0 items-center gap-2" data-testid="tournament-cell-org">
      <div
        className="flex size-6 shrink-0 overflow-hidden rounded-sm"
        aria-hidden
        data-testid="tournament-card-org-media"
      >
        {media}
      </div>
      <span
        className={cn(
          'text-sm font-medium',
          hasOrg ? 'text-text-secondary' : 'text-muted-foreground',
          CELL_TRUNCATE,
        )}
        title={label}
      >
        {label}
      </span>
    </div>
  );
});

export const TournamentCard: React.FC<Props> = React.memo(({
  tournament,
  animationIndex = 0,
  bucket,
  signupsOpen = false,
}) => {
  const navigate = useNavigate();
  const currentUser = useUserStore((state) => state.currentUser);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const now = new Date();
  const live = isTournamentLive(tournament, now, bucket);
  const shownState = displayState(tournament, now, bucket);
  const tone = stateTone(shownState);
  const league = leagueInfo(tournament);

  const headerContent = () => {
    if (!tournament || !tournament.name) return null;
    return (
      <>
        <CardTitle className="text-base truncate">
          {tournament.name}
        </CardTitle>
        <CardDescription className="flex min-w-0 items-center gap-2">
          {live && (
            <Badge
              variant="outline"
              data-testid="tournament-live-badge"
              className="h-5 shrink-0 gap-1 bg-primary/20 py-0 leading-none text-primary border-primary/30"
            >
              <span aria-hidden className="size-1.5 rounded-full bg-primary motion-safe:animate-pulse" />
              Live
            </Badge>
          )}
          {signupsOpen && (
            <Badge
              variant="outline"
              data-testid="tournament-signups-open-badge"
              className="h-5 shrink-0 gap-1 border-success/30 bg-success/20 py-0 leading-none text-success"
            >
              <UserPlus className="size-3" aria-hidden />
              Signups open
            </Badge>
          )}
          <OrgCell key={league?.organization_logo || 'none'} league={league} />
        </CardDescription>
      </>
    );
  };

  // Helper to extract time from date_played (ISO datetime string)
  const getTimeFromDate = (dateStr: string | null): string => {
    if (!dateStr) return '';
    try {
      const date = new Date(dateStr);
      return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
    } catch {
      return '';
    }
  };

  const getDateFromDate = (dateStr: string | null): string => {
    if (!dateStr) return '';
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    } catch {
      return '';
    }
  };

  // Helper to format timezone for display
  const formatTimezone = (tz: string | undefined): string => {
    if (!tz) return 'UTC';
    // Extract the last part after '/' for cleaner display
    const parts = tz.split('/');
    return parts[parts.length - 1].replace('_', ' ');
  };

  const viewMode = () => {
    return (
      <div className="flex flex-col gap-1.5">
        {/* Top row: Date and Time/Timezone */}
        <div className="grid grid-cols-1 min-[360px]:grid-cols-2 gap-1">
          {tournament.date_played && (
            <Item size="sm" variant="muted" className="!p-1.5 min-w-0">
              <ItemMedia variant="icon" className="!size-6 bg-info/20 border-info/30">
                <Calendar className="size-3 text-info" aria-hidden />
              </ItemMedia>
              <ItemContent className="!gap-0 min-w-0">
                <ItemTitle className="!text-xs text-muted-foreground">Date</ItemTitle>
                <span className={cn('text-sm', CELL_WRAP)} title={tournament.date_played} data-testid="tournament-card-date">
                  {getDateFromDate(tournament.date_played)}
                </span>
              </ItemContent>
            </Item>
          )}
          <Item size="sm" variant="muted" className="!p-1.5 min-w-0">
            <ItemMedia variant="icon" className="!size-6 bg-primary/20 border-primary/30">
              <Clock className="size-3 text-primary" aria-hidden />
            </ItemMedia>
            <ItemContent className="!gap-0 min-w-0">
              <ItemTitle className="!text-xs text-muted-foreground">Time</ItemTitle>
              <span className={cn('text-sm', CELL_WRAP)} title={`${getTimeFromDate(tournament.date_played)} (${tournament.timezone || 'UTC'})`} data-testid="tournament-card-time">
                {`${getTimeFromDate(tournament.date_played)} ${formatTimezone(tournament.timezone)}`}
              </span>
            </ItemContent>
          </Item>
        </div>

        {/* Second row: Style */}
        {tournament.tournament_type && (
          <Item size="sm" variant="muted" className="!p-1.5 min-w-0">
            <ItemMedia variant="icon" className="!size-6 bg-secondary/20 border-secondary/30">
              <Swords className="size-3 text-secondary" aria-hidden />
            </ItemMedia>
            <ItemContent className="!gap-0 min-w-0">
              <ItemTitle className="!text-xs text-muted-foreground">Style</ItemTitle>
              <span className={cn('text-sm capitalize', CELL_WRAP)} title={tournament.tournament_type.replace('_', ' ')}>
                {tournament.tournament_type.replace('_', ' ')}
              </span>
            </ItemContent>
          </Item>
        )}

        <LeagueCell league={typeof tournament.league === 'number' ? tournament.league : league} />

        {/* Third row: State and Players */}
        <div className="grid grid-cols-1 min-[360px]:grid-cols-2 gap-1">
          {tournament.state && (
            <Item size="sm" variant="muted" className="!p-1.5 min-w-0">
              <ItemMedia
                variant="icon"
                className={cn('!size-6', STATE_TILE_CLASSES[tone].media)}
                data-testid="tournament-card-state-media"
                data-tone={tone}
              >
                <Crown className={cn('size-3', STATE_TILE_CLASSES[tone].icon)} aria-hidden />
              </ItemMedia>
              <ItemContent className="!gap-0 min-w-0">
                <ItemTitle className="!text-xs text-muted-foreground">State</ItemTitle>
                <span
                  className={cn('text-sm', shownState.muted && 'text-muted-foreground', CELL_WRAP)}
                  title={shownState.label}
                  data-testid="tournament-card-state"
                >
                  {shownState.label}
                </span>
              </ItemContent>
            </Item>
          )}

          {/* Players count */}
          <Item size="sm" variant="muted" className="!p-1.5 min-w-0">
            <ItemMedia variant="icon" className="!size-6 bg-accent/20 border-accent/30">
              <Users className="size-3 text-accent" aria-hidden />
            </ItemMedia>
            <ItemContent className="!gap-0 min-w-0">
              <ItemTitle className="!text-xs text-muted-foreground">Players</ItemTitle>
              <span className="text-sm font-medium">{tournament.user_count ?? tournament.users?.length ?? 0}</span>
            </ItemContent>
          </Item>
        </div>
      </div>
    );
  };

  const ActionButtons = () => {
    const showEditBtn = currentUser?.is_staff;

    return (
      <>
        {showEditBtn && (
          <EditIconButton
            onClick={() => setEditModalOpen(true)}
            tooltip="Edit Tournament"
            data-testid="tournament-edit-button"
          />
        )}
      </>
    );
  };
  return (
    <>
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.15, delay: Math.min(animationIndex * 0.02, 0.2) }}
        className={TOURNAMENT_CARD_CELL}
        whileHover={{ scale: 1.02 }}
      >
        <div
          className={cn(
            TOURNAMENT_CARD_SURFACE,
            'hover:bg-base-200 focus:outline-2 focus:outline-offset-2 focus:outline-primary active:bg-base-200',
          )}
          data-testid={`tournament-card-${tournament.pk}`}
        >
          {/* Header: 2-col layout with name/type left, actions right */}
          <CardHeader className="p-0 gap-0.5">
            {headerContent()}
            <CardAction className="flex items-center gap-1">
              <ActionButtons />
            </CardAction>
          </CardHeader>

          {/* Card content */}
          <div className="mt-2">
            {viewMode()}
          </div>

          {/* Footer */}
          <div className="flex flex-row mt-auto pt-2 items-center justify-between">
            <PrimaryButton
              size="sm"
              onClick={() => navigate(`/tournament/${tournament.pk}`)}
              data-testid={`tournament-view-${tournament.pk}`}
            >
              <Eye className="size-4" aria-hidden />
              View Tournament
            </PrimaryButton>
            <TournamentRemoveButton tournament={tournament} />
          </div>
        </div>
      </motion.div>

      {/* Edit Modal */}
      <TournamentEditModal
        open={editModalOpen}
        onOpenChange={setEditModalOpen}
        tournament={tournament}
      />
    </>
  );
}, (prevProps, nextProps) => {
  const prev = prevProps.tournament;
  const next = nextProps.tournament;
  const prevLeague = leagueInfo(prev);
  const nextLeague = leagueInfo(next);
  return (
    prev.pk === next.pk &&
    prev.name === next.name &&
    prev.state === next.state &&
    prev.date_played === next.date_played &&
    prev.tournament_type === next.tournament_type &&
    leagueId(prev) === leagueId(next) &&
    prevLeague?.name === nextLeague?.name &&
    prevLeague?.organization_id === nextLeague?.organization_id &&
    prevLeague?.organization_name === nextLeague?.organization_name &&
    prevLeague?.organization_logo === nextLeague?.organization_logo &&
    prev.user_count === next.user_count &&
    prevProps.animationIndex === nextProps.animationIndex &&
    prevProps.bucket === nextProps.bucket &&
    prevProps.signupsOpen === nextProps.signupsOpen
  );
});
