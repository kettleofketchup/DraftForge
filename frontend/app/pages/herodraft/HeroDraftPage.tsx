import React, { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import axios from '~/components/api/axios';
import { useUserStore } from '~/store/userStore';
import { getLogger } from '~/lib/logger';

const log = getLogger('HeroDraftPage');

// Types for HeroDraft API response
interface Captain {
  pk: number;
  username: string;
  discordId: string;
  avatar?: string;
}

interface DraftTeam {
  id: number;
  tournament_team: number;
  captain: Captain | null;
  team_name: string;
  is_ready: boolean;
  is_connected: boolean;
  is_first_pick: boolean | null;
  is_radiant: boolean | null;
  reserve_time_remaining: number;
}

interface HeroDraftRound {
  id: number;
  round_number: number;
  action_type: 'ban' | 'pick';
  draft_team: number;
  hero_id: number | null;
  state: 'pending' | 'active' | 'completed';
}

interface HeroDraft {
  id: number;
  game: number;
  state: 'waiting_for_captains' | 'rolling' | 'choosing' | 'drafting' | 'paused' | 'completed' | 'abandoned';
  roll_winner: DraftTeam | null;
  draft_teams: DraftTeam[];
  rounds: HeroDraftRound[];
  current_round: HeroDraftRound | null;
  created_at: string;
  updated_at: string;
}

const formatTime = (ms: number): string => {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
};

export const HeroDraftPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const currentUser = useUserStore((state) => state.currentUser);
  const [draft, setDraft] = useState<HeroDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [ws, setWs] = useState<WebSocket | null>(null);

  // Fetch draft data
  const fetchDraft = useCallback(async () => {
    if (!id) return;
    try {
      const response = await axios.get(`/herodraft/${id}/`);
      setDraft(response.data);
      setError(null);
    } catch (err) {
      log.error('Failed to fetch draft:', err);
      setError('Failed to load hero draft');
    } finally {
      setLoading(false);
    }
  }, [id]);

  // Connect to WebSocket
  useEffect(() => {
    if (!id) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/api/herodraft/${id}/`;

    log.info('Connecting to WebSocket:', wsUrl);
    const websocket = new WebSocket(wsUrl);

    websocket.onopen = () => {
      log.info('WebSocket connected');
    };

    websocket.onmessage = (event) => {
      log.debug('WebSocket message:', event.data);
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'draft_update' || data.draft) {
          // Refetch draft on update
          fetchDraft();
        }
      } catch (e) {
        log.error('Failed to parse WebSocket message:', e);
      }
    };

    websocket.onerror = (error) => {
      log.error('WebSocket error:', error);
    };

    websocket.onclose = () => {
      log.info('WebSocket disconnected');
    };

    setWs(websocket);

    return () => {
      websocket.close();
    };
  }, [id, fetchDraft]);

  // Initial fetch
  useEffect(() => {
    fetchDraft();
  }, [fetchDraft]);

  // Check if current user is a captain
  const getCurrentUserTeam = (): DraftTeam | null => {
    if (!draft || !currentUser) return null;
    return draft.draft_teams.find(
      (team) => team.captain?.pk === currentUser.pk
    ) || null;
  };

  const userTeam = getCurrentUserTeam();
  const isCaptain = !!userTeam;

  // Handle ready button click
  const handleReady = async () => {
    if (!id) return;
    try {
      await axios.post(`/herodraft/${id}/set-ready/`);
      fetchDraft();
    } catch (err) {
      log.error('Failed to set ready:', err);
    }
  };

  // Handle trigger roll
  const handleTriggerRoll = async () => {
    if (!id) return;
    try {
      await axios.post(`/herodraft/${id}/trigger-roll/`);
      fetchDraft();
    } catch (err) {
      log.error('Failed to trigger roll:', err);
    }
  };

  // Handle choice submission
  const handleSubmitChoice = async (choiceType: 'pick_order' | 'side', value: string) => {
    if (!id) return;
    try {
      await axios.post(`/herodraft/${id}/submit-choice/`, {
        choice_type: choiceType,
        value,
      });
      fetchDraft();
    } catch (err) {
      log.error('Failed to submit choice:', err);
    }
  };

  // Handle hero pick/ban
  const handleSubmitPick = async (heroId: number) => {
    if (!id) return;
    try {
      await axios.post(`/herodraft/${id}/submit-pick/`, {
        hero_id: heroId,
      });
      fetchDraft();
    } catch (err) {
      log.error('Failed to submit pick:', err);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-screen">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (error || !draft) {
    return (
      <div className="flex justify-center items-center h-screen">
        <div role="alert" className="alert alert-error">
          <span>{error || 'Draft not found'}</span>
        </div>
      </div>
    );
  }

  const teamA = draft.draft_teams[0];
  const teamB = draft.draft_teams[1];

  return (
    <div className="min-h-screen bg-base-200 p-4">
      <div
        className="modal modal-open"
        data-testid="herodraft-modal"
      >
        <div className="modal-box max-w-4xl">
          {/* Top Bar */}
          <div
            className="flex justify-between items-center mb-4 p-4 bg-base-300 rounded-lg"
            data-testid="herodraft-topbar"
          >
            {/* Team A */}
            <div className="flex flex-col items-center">
              <span
                className="font-bold text-lg"
                data-testid="herodraft-team-a-captain"
              >
                {teamA?.captain?.username || 'Unknown'}
              </span>
              <span
                className="text-sm opacity-70"
                data-testid="herodraft-team-a-reserve-time"
              >
                {formatTime(teamA?.reserve_time_remaining || 0)}
              </span>
            </div>

            {/* VS */}
            <div className="text-2xl font-bold">VS</div>

            {/* Team B */}
            <div className="flex flex-col items-center">
              <span
                className="font-bold text-lg"
                data-testid="herodraft-team-b-captain"
              >
                {teamB?.captain?.username || 'Unknown'}
              </span>
              <span
                className="text-sm opacity-70"
                data-testid="herodraft-team-b-reserve-time"
              >
                {formatTime(teamB?.reserve_time_remaining || 0)}
              </span>
            </div>
          </div>

          {/* WebSocket Status */}
          <div className="mb-4">
            <span
              className={`badge ${ws?.readyState === WebSocket.OPEN ? 'badge-success' : 'badge-error'}`}
              data-testid="herodraft-ws-status"
            >
              {ws?.readyState === WebSocket.OPEN ? 'Connected' : 'Disconnected'}
            </span>
          </div>

          {/* Waiting Phase */}
          {draft.state === 'waiting_for_captains' && (
            <div data-testid="herodraft-waiting-phase">
              <h2 className="text-xl font-bold mb-4" data-testid="herodraft-waiting-title">
                Waiting for Captains
              </h2>

              {/* Captain Status List */}
              <div
                className="space-y-2"
                data-testid="herodraft-captain-status-list"
              >
                {draft.draft_teams.map((team) => (
                  <div
                    key={team.id}
                    className={`flex justify-between items-center p-3 rounded-lg ${
                      team.is_ready ? 'bg-success/20' : 'bg-base-300'
                    }`}
                    data-testid={`herodraft-captain-status-${team.id}`}
                  >
                    <span>{team.captain?.username || 'Unknown'}</span>
                    <span
                      className={`badge ${team.is_ready ? 'badge-success' : 'badge-warning'}`}
                      data-testid={`herodraft-ready-status-${team.id}`}
                    >
                      {team.is_ready ? 'Ready' : 'Not Ready'}
                    </span>
                  </div>
                ))}
              </div>

              {/* Ready Button */}
              {isCaptain && !userTeam?.is_ready && (
                <button
                  className="btn btn-primary mt-4 w-full"
                  onClick={handleReady}
                  data-testid="herodraft-ready-button"
                >
                  Ready
                </button>
              )}
            </div>
          )}

          {/* Rolling Phase */}
          {draft.state === 'rolling' && (
            <div data-testid="herodraft-rolling-phase">
              <h2 className="text-xl font-bold mb-4" data-testid="herodraft-rolling-title">
                Both Captains Ready!
              </h2>
              <p className="mb-4" data-testid="herodraft-rolling-instruction">
                Click to flip the coin and determine who chooses first.
              </p>

              {isCaptain && (
                <button
                  className="btn btn-primary w-full"
                  onClick={handleTriggerRoll}
                  data-testid="herodraft-flip-coin-button"
                >
                  Flip Coin
                </button>
              )}
            </div>
          )}

          {/* Choosing Phase */}
          {draft.state === 'choosing' && (
            <div data-testid="herodraft-choosing-phase">
              <h2 className="text-xl font-bold mb-4">Make Your Choice</h2>

              {draft.roll_winner && (() => {
                const winnerTeam = draft.roll_winner;
                const loserTeam = draft.draft_teams.find(t => t.id !== winnerTeam.id);
                const isWinner = userTeam?.id === winnerTeam.id;
                const isLoser = userTeam && userTeam.id !== winnerTeam.id;

                return (
                  <>
                    <p className="mb-4 text-lg" data-testid="herodraft-flip-winner">
                      {winnerTeam.captain?.username} won the flip!
                    </p>

                    {/* Winner's choices - only show if they haven't made a choice yet */}
                    {isWinner && winnerTeam.is_first_pick === null && winnerTeam.is_radiant === null && (
                      <div className="space-y-4" data-testid="herodraft-winner-choices">
                        <p className="text-sm opacity-70">Choose your preference:</p>
                        <div className="flex gap-4" data-testid="herodraft-choice-buttons">
                          <button
                            className="btn btn-primary flex-1"
                            onClick={() => handleSubmitChoice('pick_order', 'first')}
                            data-testid="herodraft-choice-first-pick"
                          >
                            First Pick
                          </button>
                          <button
                            className="btn btn-secondary flex-1"
                            onClick={() => handleSubmitChoice('pick_order', 'second')}
                            data-testid="herodraft-choice-second-pick"
                          >
                            Second Pick
                          </button>
                          <button
                            className="btn btn-accent flex-1"
                            onClick={() => handleSubmitChoice('side', 'radiant')}
                            data-testid="herodraft-choice-radiant"
                          >
                            Radiant
                          </button>
                          <button
                            className="btn btn-neutral flex-1"
                            onClick={() => handleSubmitChoice('side', 'dire')}
                            data-testid="herodraft-choice-dire"
                          >
                            Dire
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Winner waiting for loser to choose */}
                    {isWinner && (winnerTeam.is_first_pick !== null || winnerTeam.is_radiant !== null) && (
                      <p className="text-sm opacity-70" data-testid="herodraft-winner-waiting">
                        Waiting for opponent to make their choice...
                      </p>
                    )}

                    {/* Loser's remaining choices */}
                    {isLoser && (
                      <div className="space-y-4" data-testid="herodraft-loser-choices">
                        <p className="text-sm opacity-70">Choose the remaining option:</p>
                        <div className="flex gap-4" data-testid="herodraft-remaining-choice-buttons">
                          {/* Show pick order buttons if winner chose side */}
                          {winnerTeam?.is_first_pick === null && (
                            <>
                              <button
                                className="btn btn-primary flex-1"
                                onClick={() => handleSubmitChoice('pick_order', 'first')}
                                data-testid="herodraft-remaining-first-pick"
                              >
                                First Pick
                              </button>
                              <button
                                className="btn btn-secondary flex-1"
                                onClick={() => handleSubmitChoice('pick_order', 'second')}
                                data-testid="herodraft-remaining-second-pick"
                              >
                                Second Pick
                              </button>
                            </>
                          )}
                          {/* Show side buttons if winner chose pick order */}
                          {winnerTeam?.is_radiant === null && (
                            <>
                              <button
                                className="btn btn-accent flex-1"
                                onClick={() => handleSubmitChoice('side', 'radiant')}
                                data-testid="herodraft-remaining-radiant"
                              >
                                Radiant
                              </button>
                              <button
                                className="btn btn-neutral flex-1"
                                onClick={() => handleSubmitChoice('side', 'dire')}
                                data-testid="herodraft-remaining-dire"
                              >
                                Dire
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Spectator view */}
                    {!isCaptain && (
                      <p className="text-sm opacity-70" data-testid="herodraft-spectating">
                        Spectating...
                      </p>
                    )}
                  </>
                );
              })()}
            </div>
          )}

          {/* Drafting Phase */}
          {draft.state === 'drafting' && (
            <div data-testid="herodraft-drafting-phase">
              <h2 className="text-xl font-bold mb-4">
                {draft.current_round?.action_type === 'ban' ? 'Ban Phase' : 'Pick Phase'}
              </h2>

              <div className="mb-4" data-testid="herodraft-current-round">
                <p>Round: {draft.current_round?.round_number || 'N/A'}</p>
                <p>Action: {draft.current_round?.action_type || 'N/A'}</p>
              </div>

              {/* Hero Grid Placeholder - would need hero data */}
              <div
                className="grid grid-cols-10 gap-2 mb-4"
                data-testid="herodraft-hero-grid"
              >
                {/* Placeholder for hero icons */}
                <div className="text-center text-sm opacity-50 col-span-10">
                  Hero selection grid will appear here
                </div>
              </div>

              {/* Picked/Banned Heroes */}
              <div className="flex justify-between">
                <div data-testid="herodraft-team-a-picks">
                  <h3 className="font-bold mb-2">{teamA?.captain?.username}'s Picks</h3>
                  <div className="flex gap-2">
                    {draft.rounds
                      .filter(r => r.draft_team === teamA?.id && r.state === 'completed' && r.action_type === 'pick')
                      .map(r => (
                        <div key={r.id} className="badge badge-primary">
                          Hero {r.hero_id}
                        </div>
                      ))}
                  </div>
                </div>
                <div data-testid="herodraft-team-b-picks">
                  <h3 className="font-bold mb-2">{teamB?.captain?.username}'s Picks</h3>
                  <div className="flex gap-2">
                    {draft.rounds
                      .filter(r => r.draft_team === teamB?.id && r.state === 'completed' && r.action_type === 'pick')
                      .map(r => (
                        <div key={r.id} className="badge badge-secondary">
                          Hero {r.hero_id}
                        </div>
                      ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Completed Phase */}
          {draft.state === 'completed' && (
            <div data-testid="herodraft-completed-phase">
              <h2 className="text-xl font-bold mb-4">Draft Complete!</h2>
              <p>The hero draft has been completed.</p>
            </div>
          )}

          {/* Abandoned Phase */}
          {draft.state === 'abandoned' && (
            <div data-testid="herodraft-abandoned-phase">
              <h2 className="text-xl font-bold mb-4 text-error">Draft Abandoned</h2>
              <p>This draft has been abandoned.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default HeroDraftPage;
