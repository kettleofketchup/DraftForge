import { describe, expect, it } from 'vitest';
import {
  buildSignupModalBanner,
  buildSignupModalTitle,
} from '../EventSignupModal';

// Pure-helper tests for the intent→copy interpolation. Form interaction is
// in the event-signup-form Playwright spec.

describe('buildSignupModalTitle', () => {
  it('uses the "Sign Up" copy for rsvp intent', () => {
    expect(buildSignupModalTitle('rsvp', 'Evt')).toBe('Sign Up for Evt');
  });

  it('uses the "Mark Tentative" copy for tentative intent', () => {
    expect(buildSignupModalTitle('tentative', 'Evt')).toBe(
      'Mark Tentative for Evt',
    );
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
    expect(buildSignupModalBanner('tentative')).toContain(
      'interested but not committed',
    );
  });
});
