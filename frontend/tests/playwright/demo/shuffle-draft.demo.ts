/**
 * Shuffle Draft Demo - Full Flow Video Recording
 *
 * Records a complete shuffle MMR draft from start to finish for documentation.
 * Shuffle draft has MMR-based double pick mechanics where lower MMR teams
 * can get consecutive picks if they stay under the threshold.
 *
 * Video output: 1:1 aspect ratio (1200x1200) for docs and social media.
 * Named output: shuffle_draft.webm
 */

import { test } from '@playwright/test';
import { runDraftDemo } from './draft-demo-helper';
import * as path from 'path';
import { fileURLToPath } from 'url';

// ESM-compatible __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test.describe('Shuffle Draft Demo', () => {
  test('Complete Shuffle MMR Draft Flow', async ({}) => {
    test.setTimeout(300_000);

    await runDraftDemo({
      tournamentKey: 'demo_shuffle_draft',
      draftStyle: 'shuffle',
      outputName: 'shuffle_draft',
      docsVideoDir: path.resolve(__dirname, '../../../docs/assets/videos'),
    });
  });
});
