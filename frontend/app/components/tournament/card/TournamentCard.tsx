import React, { useState } from 'react';
import type { TournamentType } from '~/components/tournament/types';
import { STATE_CHOICES } from '../constants';

import { Building2, Calendar, Clock, Crown, Swords, Trophy, Users } from 'lucide-react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router';
import { useUserStore } from '~/store/userStore';
import { EditIconButton, ViewIconButton } from '../../ui/buttons';
import {
  CardAction,
  CardDescription,
  CardHeader,
  CardTitle,
} from '../../ui/card';
import { Item, ItemContent, ItemMedia, ItemTitle } from '../../ui/item';
import { TournamentRemoveButton } from './deleteButton';
import { TournamentEditModal } from './TournamentEditModal';
interface Props {
  tournament: TournamentType;
  /** Animation delay index for staggered loading */
  animationIndex?: number;
}

/** Truncate text to max 12 characters with ellipsis */
const truncateText = (text: string, maxLength = 12): string => {
  if (!text) return '';
  return text.length > maxLength ? `${text.slice(0, maxLength)}…` : text;
};

export const TournamentCard: React.FC<Props> = React.memo(({
  tournament,
  animationIndex = 0,
}) => {
  const navigate = useNavigate();
  const currentUser = useUserStore((state) => state.currentUser);
  const [editModalOpen, setEditModalOpen] = useState(false);

  const getHeaderName = () => {
    return tournament.name || '';
  };

  const TournamentHeaderContent = () => {
    if (!tournament || !tournament.name) return null;
    return (
      <>
        <CardTitle className="text-base truncate">
          {getHeaderName()}
        </CardTitle>
        <CardDescription className="text-xs text-muted-foreground">
          Tournament
        </CardDescription>
      </>
    );
  };
  // Helper for League display with avatar
  const LeagueItem = () => {
    // League can be a number (ID) or an object with league details
    const leagueData = typeof tournament.league === 'object'
      ? (tournament.league as unknown as { pk?: number; name?: string; organization_name?: string })
      : null;
    const hasLeague = tournament.league != null;
    const leagueName = hasLeague
      ? (leagueData?.name || (typeof tournament.league === 'number' ? `League #${tournament.league}` : 'Unknown League'))
      : 'None';

    return (
      <Item size="sm" variant="muted" className={`!p-1.5 ${!hasLeague ? 'bg-red-500/20' : ''}`}>
        <ItemMedia variant="icon" className={`!size-6 ${hasLeague ? 'bg-primary/20 border-primary/30' : 'bg-red-500/30 border-red-500/40'}`}>
          <Trophy className={`h-3 w-3 ${hasLeague ? 'text-primary' : 'text-red-500'}`} />
        </ItemMedia>
        <ItemContent className="!gap-0">
          <ItemTitle className="!text-xs text-muted-foreground">League</ItemTitle>
          <span className={`text-sm font-medium ${!hasLeague ? 'text-red-500' : ''}`} title={leagueName}>{truncateText(leagueName)}</span>
        </ItemContent>
      </Item>
    );
  };

  // Helper for Organization display with avatar
  const OrganizationItem = () => {
    // Get organization from league data if available
    const leagueData = typeof tournament.league === 'object'
      ? (tournament.league as unknown as { organization_name?: string })
      : null;
    const orgName = leagueData?.organization_name;
    const hasOrg = !!orgName;

    return (
      <Item size="sm" variant="muted" className={`!p-1.5 ${!hasOrg ? 'bg-red-500/20' : ''}`}>
        <ItemMedia variant="icon" className={`!size-6 ${hasOrg ? 'bg-purple-500/20 border-purple-500/30' : 'bg-red-500/30 border-red-500/40'}`}>
          <Building2 className={`h-3 w-3 ${hasOrg ? 'text-purple-500' : 'text-red-500'}`} />
        </ItemMedia>
        <ItemContent className="!gap-0">
          <ItemTitle className="!text-xs text-muted-foreground">Organization</ItemTitle>
          <span className={`text-sm font-medium ${!hasOrg ? 'text-red-500' : ''}`} title={orgName || 'None'}>{truncateText(orgName || 'None')}</span>
        </ItemContent>
      </Item>
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
        <div className="grid grid-cols-2 gap-1">
          {tournament.date_played && (
            <Item size="sm" variant="muted" className="!p-1.5">
              <ItemMedia variant="icon" className="!size-6 bg-sky-500/20 border-sky-500/30">
                <Calendar className="h-3 w-3 text-sky-500" />
              </ItemMedia>
              <ItemContent className="!gap-0">
                <ItemTitle className="!text-xs text-muted-foreground">Date</ItemTitle>
                <span className="text-sm" title={tournament.date_played}>{truncateText(tournament.date_played)}</span>
              </ItemContent>
            </Item>
          )}
          <Item size="sm" variant="muted" className="!p-1.5">
            <ItemMedia variant="icon" className="!size-6 bg-indigo-500/20 border-indigo-500/30">
              <Clock className="h-3 w-3 text-indigo-500" />
            </ItemMedia>
            <ItemContent className="!gap-0">
              <ItemTitle className="!text-xs text-muted-foreground">Time</ItemTitle>
              <span className="text-sm" title={`${getTimeFromDate(tournament.date_played)} (${tournament.timezone || 'UTC'})`}>
                {truncateText(`${getTimeFromDate(tournament.date_played)} ${formatTimezone(tournament.timezone)}`)}
              </span>
            </ItemContent>
          </Item>
        </div>

        {/* Second row: Style */}
        {tournament.tournament_type && (
          <Item size="sm" variant="muted" className="!p-1.5">
            <ItemMedia variant="icon" className="!size-6 bg-orange-500/20 border-orange-500/30">
              <Swords className="h-3 w-3 text-orange-500" />
            </ItemMedia>
            <ItemContent className="!gap-0">
              <ItemTitle className="!text-xs text-muted-foreground">Style</ItemTitle>
              <span className="text-sm capitalize" title={tournament.tournament_type.replace('_', ' ')}>{truncateText(tournament.tournament_type.replace('_', ' '))}</span>
            </ItemContent>
          </Item>
        )}

        {/* Second row: League and Organization */}
        <div className="grid grid-cols-2 gap-1">
          <LeagueItem />
          <OrganizationItem />
        </div>

        {/* Third row: State and Players */}
        <div className="grid grid-cols-2 gap-1">
          {tournament.state && (
            <Item size="sm" variant="muted" className="!p-1.5">
              <ItemMedia variant="icon" className="!size-6 bg-emerald-500/20 border-emerald-500/30">
                <Crown className="h-3 w-3 text-emerald-500" />
              </ItemMedia>
              <ItemContent className="!gap-0">
                <ItemTitle className="!text-xs text-muted-foreground">State</ItemTitle>
                <span className="text-sm capitalize" title={STATE_CHOICES[tournament.state] || tournament.state}>{truncateText(STATE_CHOICES[tournament.state] || tournament.state)}</span>
              </ItemContent>
            </Item>
          )}

          {/* Players count */}
          <Item size="sm" variant="muted" className="!p-1.5">
            <ItemMedia variant="icon" className="!size-6 bg-cyan-500/20 border-cyan-500/30">
              <Users className="h-3 w-3 text-cyan-500" />
            </ItemMedia>
            <ItemContent className="!gap-0">
              <ItemTitle className="!text-xs text-muted-foreground">Players</ItemTitle>
              <span className="text-sm font-medium">{tournament.user_count ?? tournament.users?.length ?? 0}</span>
            </ItemContent>
          </Item>
        </div>
      </div>
    );
  };

  const getKeyName = () => {
    let result = '';
    if (tournament.pk) {
      result += tournament.pk.toString();
    }
    if (tournament.date_played) {
      result += tournament.date_played.toString();
    }
    if (tournament.name) {
      result += tournament.name;
    }
    return result;
  };

  const ActionButtons = () => {
    const showEditBtn = currentUser?.is_staff;

    return (
      <>
        {showEditBtn && (
          <EditIconButton
            onClick={() => setEditModalOpen(true)}
            tooltip="Edit Tournament"
          />
        )}
        <ViewIconButton
          onClick={() => navigate(`/tournament/${tournament.pk}`)}
          tooltip="View Tournament"
        />
      </>
    );
  };
  return (
    <>
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.15, delay: Math.min(animationIndex * 0.02, 0.2) }}
        key={`Tournamentcard:${getKeyName()} base`}
        className="flex items-center justify-center p-4 gap-6 content-center w-full h-full"
        whileHover={{ scale: 1.02 }}
      >
        <div
          className="card card-compact bg-base-300 rounded-2xl w-full max-w-sm
              hover:bg-base-200 focus:outline-2
              focus:outline-offset-2 focus:outline-primary
              active:bg-base-200"
        >
          {/* Header: 2-col layout with name/type left, actions right */}
          <CardHeader className="p-0 gap-0.5">
            <TournamentHeaderContent />
            <CardAction className="flex items-center gap-1">
              <ActionButtons />
            </CardAction>
          </CardHeader>

          {/* Card content */}
          <div className="mt-2">
            {viewMode()}
          </div>

          {/* Footer with delete button */}
          <div className="flex flex-row mt-2 justify-end">
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
  // Custom comparison - only re-render if these values actually change
  const prevLeagueId = typeof prevProps.tournament.league === 'object'
    ? prevProps.tournament.league?.pk
    : prevProps.tournament.league;
  const nextLeagueId = typeof nextProps.tournament.league === 'object'
    ? nextProps.tournament.league?.pk
    : nextProps.tournament.league;
  return (
    prevProps.tournament.pk === nextProps.tournament.pk &&
    prevProps.tournament.name === nextProps.tournament.name &&
    prevProps.tournament.state === nextProps.tournament.state &&
    prevProps.tournament.date_played === nextProps.tournament.date_played &&
    prevProps.tournament.tournament_type === nextProps.tournament.tournament_type &&
    prevLeagueId === nextLeagueId &&
    prevProps.tournament.user_count === nextProps.tournament.user_count &&
    prevProps.animationIndex === nextProps.animationIndex
  );
});
