- Adding a member to a league from the league page now seeds their league MMR from the
  Dota 2 org MMR instead of 0.
- The draft-style MMR comparison (snake vs normal vs shuffle) no longer shares one cache
  entry across all drafts and no longer serves stale values after an org MMR change.
- Approving a signup, importing a CSV and merging Discord accounts now refresh the
  tournament and draft pages that show the changed org MMR.
- The organization CSV import now clears cached member data after writing MMR.
- Editing an org MMR with an empty value no longer returns a server error; it clears the
  value. Invalid values return 400 instead of being stored.
- The MMR approval dialog on the roll-call page now shows the Dota suggested range and
  the Dota rank signals card; before, both were missing there.
- Leaving the MMR approval input empty no longer approves the signup at 0.
- Merging two Discord accounts in the same organization no longer discards the dropped
  account's org MMR: for each game the higher of the two values is kept.
