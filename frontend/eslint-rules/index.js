import { dedupeRawColors, noRawColorStrings } from './colors.js';
import userDisplay from './user-display.js';

export default {
  meta: { name: 'draftforge' },
  rules: {
    ...userDisplay.rules,
    'no-raw-color-strings': noRawColorStrings,
  },
  processors: { 'dedupe-raw-colors': dedupeRawColors },
};
