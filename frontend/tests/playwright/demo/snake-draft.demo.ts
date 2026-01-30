/**
 * Snake Draft Demo - Full Flow Video Recording
 *
 * Records a complete snake draft from start to finish for documentation.
 * Snake draft has a predictable pattern where pick order reverses each round.
 *
 * Video output: 1:1 aspect ratio (1200x1200) for docs and social media.
 * Named output: snake_draft.webm
 */

import { test } from '@playwright/test';
import { runDraftDemo } from './draft-demo-helper';
import * as path from 'path';
import { fileURLToPath } from 'url';

// ESM-compatible __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test.describe('Snake Draft Demo', () => {
  test('Complete Snake Draft Flow', async ({}) => {
    test.setTimeout(300_000);

    await runDraftDemo({
      tournamentKey: 'demo_snake_draft',
      draftStyle: 'snake',
      outputName: 'snake_draft',
      docsVideoDir: path.resolve(__dirname, '../../../docs/assets/videos'),
    });
  });
});
