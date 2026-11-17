export type ActivityScope = 'tournament' | 'draft';

export type ActivityDraftKind = 'hero' | 'team';

export type ActivityView =
  | { kind: 'team'; id: number }
  | { kind: 'hero'; id: number }
  | { kind: 'bracket' };

export type ActivityTrigger =
  | 'initial'
  | 'menu'
  | 'banner'
  | 'bracket_match'
  | 'launch_intent'
  | 'scope_lost'
  | 'kicked_recover';

export interface LaunchIntentRef {
  intent_id: string;
  kind: ActivityDraftKind;
  id: number;
}

export interface ActivityNotice {
  intent_id?: string;
  kind: ActivityDraftKind;
  draft_id: number;
  tournament_name: string | null;
  label: string;
  url: string;
}

export type DraftStatus = 'waiting' | 'drafting' | 'paused' | 'finished';
export type ActivityRole = 'captain' | 'player' | 'staff' | 'spectator';

export interface ActivityTeamDraftEntry {
  id: number;
  state: string;
  status: DraftStatus;
  involves_me: boolean;
  role: ActivityRole;
}

export interface ActivityHeroDraftEntry extends ActivityTeamDraftEntry {
  game_id: number;
  label: string;
  updated_at: string;
}

export interface ActivityDraftList {
  tournament: { id: number; name: string } | null;
  team_draft: ActivityTeamDraftEntry | null;
  hero_drafts: ActivityHeroDraftEntry[];
  launch_intent: LaunchIntentRef | null;
  notice: ActivityNotice | null;
  site_url: string;
}

export type ActivityViewEvent =
  | {
      action: 'view';
      from?: ActivityView;
      to: ActivityView;
      trigger: ActivityTrigger;
      intent_id?: string;
    }
  | { action: 'notice_seen'; intent_id?: string }
  | { action: 'intent_declined'; intent_id: string }
  | { action: 'open_external'; view: ActivityView };
