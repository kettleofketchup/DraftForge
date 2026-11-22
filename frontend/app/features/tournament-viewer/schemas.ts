import { z } from 'zod';

// backend/app/views_main.py TournamentView.viewer
export const TournamentViewerSchema = z.object({
  can_edit_tournament: z.boolean(),
});

export type TournamentViewer = z.infer<typeof TournamentViewerSchema>;
