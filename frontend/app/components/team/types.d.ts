import { TeamSchema } from './schemas';
export type TeamType = z.infer<typeof TeamSchema>;
