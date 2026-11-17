import type { Config } from '@react-router/dev/config';

import { PRERENDER_PATHS } from './app/lib/prerender';

export default {
  ssr: true,
  prerender: [...PRERENDER_PATHS],
} satisfies Config;
