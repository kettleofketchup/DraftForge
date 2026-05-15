import { describe, it, expect } from 'vitest';
import {
  buildSignupModalBanner,
  buildSignupModalTitle,
} from '../EventSignupModal';

// The modal's content lives inside a Radix Dialog portal, so
// renderToStaticMarkup can't see it in a node test environment (no
// document.body). These pure-helper smoke tests cover the intent→copy
// interpolation that the modal exposes; full DOM rendering (Dialog open
// state, form interaction) is exercised by Playwright in
// frontend/tests/playwright/e2e/16-events/12-event-signup-form.spec.ts.

describe('buildSignupModalTitle', () => {
  it('uses the "Sign Up" copy for rsvp intent', () => {
    expect(buildSignupModalTitle('rsvp', 'Evt')).toBe('Sign Up for Evt');
  });

  it('uses the "Mark Tentative" copy for tentative intent', () => {
    expect(buildSignupModalTitle('tentative', 'Evt')).toBe('Mark Tentative for Evt');
  });

  it('interpolates the event name verbatim', () => {
    expect(buildSignupModalTitle('rsvp', 'Friday Night Inhouse #42')).toBe(
      'Sign Up for Friday Night Inhouse #42',
    );
  });
});

describe('buildSignupModalBanner', () => {
  it('rsvp banner mentions committing to play', () => {
    expect(buildSignupModalBanner('rsvp')).toContain('committing to play');
  });

  it('tentative banner mentions interested but not committed', () => {
    expect(buildSignupModalBanner('tentative')).toContain('interested but not committed');
  });
});
