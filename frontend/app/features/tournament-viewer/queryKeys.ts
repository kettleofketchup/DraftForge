export const tournamentViewerKeys = {
  detail: (tournamentPk: number, viewerPk: number | null) =>
    ['tournament-viewer', tournamentPk, viewerPk] as const,
};
