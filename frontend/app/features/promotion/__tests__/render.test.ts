import { describe, expect, it } from 'vitest';
import { PLACEHOLDER_KEYS, renderTemplate, sampleContext } from '../render';
import fixture from './render_fixture.json';

describe('renderTemplate fixture parity', () => {
  for (const c of fixture.cases) {
    it(c.name, () => {
      expect(renderTemplate(c.body, fixture.context)).toEqual({
        text: c.text,
        warnings: c.warnings,
      });
    });
  }

  it('fixture context covers exactly the placeholder keys', () => {
    expect(Object.keys(fixture.context).sort()).toEqual(
      [...PLACEHOLDER_KEYS].sort(),
    );
  });
});

describe('PLACEHOLDER_KEYS', () => {
  it('lists the ten placeholders in spec order', () => {
    expect(PLACEHOLDER_KEYS).toEqual([
      'player',
      'promoter',
      'event',
      'event_time',
      'event_time_relative',
      'event_date',
      'signups_open',
      'event_link',
      'org',
      'discord_link',
    ]);
  });
});

describe('renderTemplate', () => {
  it('leaves a whitelisted token literal when the context lacks it', () => {
    expect(renderTemplate('Hi {player} {event}', { player: 'Ann' })).toEqual({
      text: 'Hi Ann {event}',
      warnings: [],
    });
  });
});

describe('sampleContext', () => {
  const event = {
    id: 42,
    name: 'Friday Inhouse',
    scheduled_at: '2026-11-15T01:00:00Z',
    signups_open_at: '2026-11-10T01:00:00Z',
  };
  const org = {
    name: 'Kettle Club',
    discord_link: 'https://discord.gg/kettle',
  };
  const sender = {
    username: 'bob',
    nickname: 'Bobby',
    discordNickname: null,
    guildNickname: 'Bob',
  };

  it('fills every placeholder key', () => {
    const ctx = sampleContext(event, org, sender, 'https://dota.example');
    expect(Object.keys(ctx).sort()).toEqual([...PLACEHOLDER_KEYS].sort());
  });

  it('uses Discord timestamp codes for the event times', () => {
    const ctx = sampleContext(event, org, sender, 'https://dota.example');
    expect(ctx.event_time).toBe('<t:1794704400:F>');
    expect(ctx.event_time_relative).toBe('<t:1794704400:R>');
    expect(ctx.event_date).toBe('<t:1794704400:D>');
    expect(ctx.signups_open).toBe('<t:1794272400:R>');
  });

  it('fills names and links like the backend context', () => {
    const ctx = sampleContext(event, org, sender, 'https://dota.example');
    expect(ctx.promoter).toBe('Bob');
    expect(ctx.event).toBe('Friday Inhouse');
    expect(ctx.event_link).toBe('https://dota.example/events/42');
    expect(ctx.org).toBe('Kettle Club');
    expect(ctx.discord_link).toBe('https://discord.gg/kettle');
    expect(ctx.player).not.toBe('');
  });

  it('falls back through the sender name chain', () => {
    const ctx = sampleContext(
      event,
      org,
      { username: 'bob', nickname: 'Bobby' },
      'https://x',
    );
    expect(ctx.promoter).toBe('Bobby');
    expect(
      sampleContext(event, org, { username: 'bob' }, 'https://x').promoter,
    ).toBe('bob');
  });

  it('leaves signups_open and discord_link empty when unset', () => {
    const ctx = sampleContext(
      { ...event, signups_open_at: null },
      { name: 'Org' },
      null,
      'https://x',
    );
    expect(ctx.signups_open).toBe('');
    expect(ctx.discord_link).toBe('');
    expect(ctx.promoter).toBe('');
  });

  it('leaves the time placeholders empty for a malformed date', () => {
    const ctx = sampleContext(
      { ...event, scheduled_at: 'not-a-date', signups_open_at: 'nope' },
      org,
      sender,
      'https://x',
    );
    expect(ctx.event_time).toBe('');
    expect(ctx.event_time_relative).toBe('');
    expect(ctx.event_date).toBe('');
    expect(ctx.signups_open).toBe('');
  });
});
