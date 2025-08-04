export interface CreateTeamFromCaptainAPI {
  tournament_pk: number;
  user_pk: number;
  draft_order?: number;
}

export interface InitDraftRoundsAPI {
  tournament_pk: number;
}


export interface RebuildDraftRoundsAPI {
  tournament_pk: number;
}
