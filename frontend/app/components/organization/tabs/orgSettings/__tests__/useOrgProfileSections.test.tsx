// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from '@testing-library/react';
import type { ReactNode, RefObject } from 'react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { updateOrganization } from '~/components/api/api';
import type { OrganizationType } from '~/components/organization/schemas';
import type { SettingsDialogHandle } from '~/components/patterns/SettingsDialog';
import type { SettingsFormUnit } from '~/components/patterns/settingsSaveBar';
import { useOrgProfileSections } from '../useOrgProfileSections';

vi.mock('~/components/api/api', () => ({ updateOrganization: vi.fn() }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
});

const ORG = {
  pk: 7,
  name: 'Org',
  description: '',
  logo: '',
  timezone: 'America/New_York',
} as OrganizationType;

const selectSection = vi.fn();
const sectionsRef = {
  current: {
    selectSection,
    sectionOfField: () => 'general',
  },
} as unknown as RefObject<SettingsDialogHandle<string> | null>;

let unit: SettingsFormUnit;

function Harness(): ReactNode {
  const { sections, unit: u } = useOrgProfileSections(ORG, sectionsRef);
  unit = u;
  return <div>{sections.find((s) => s.value === 'general')?.content}</div>;
}

function renderHarness() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <Harness />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.mocked(updateOrganization).mockReset();
  selectSection.mockReset();
});

describe('useOrgProfileSections unit', () => {
  it('unit.isDirty flips after editing name', () => {
    renderHarness();
    expect(unit.isDirty).toBe(false);
    fireEvent.change(screen.getByTestId('org-name-input'), {
      target: { value: 'New' },
    });
    expect(unit.isDirty).toBe(true);
  });

  it('unit.save PATCHes via updateOrganization and resolves true', async () => {
    vi.mocked(updateOrganization).mockResolvedValue(ORG);
    renderHarness();
    fireEvent.change(screen.getByTestId('org-name-input'), {
      target: { value: 'New' },
    });
    let ok = false;
    await act(async () => {
      ok = await unit.save();
    });
    expect(ok).toBe(true);
    expect(updateOrganization).toHaveBeenCalledWith(
      7,
      expect.objectContaining({ name: 'New' }),
    );
    expect(unit.isDirty).toBe(false);
  });

  it('unit.save resolves false and selects the section on an invalid logo URL', async () => {
    renderHarness();
    fireEvent.change(screen.getByTestId('org-logo-input'), {
      target: { value: 'not a url' },
    });
    let ok = true;
    await act(async () => {
      ok = await unit.save();
    });
    expect(ok).toBe(false);
    expect(updateOrganization).not.toHaveBeenCalled();
    expect(selectSection).toHaveBeenCalledWith('general');
  });

  it('discard restores organization values', () => {
    renderHarness();
    fireEvent.change(screen.getByTestId('org-name-input'), {
      target: { value: 'New' },
    });
    act(() => unit.discard());
    expect(unit.isDirty).toBe(false);
    expect(screen.getByTestId('org-name-input')).toHaveValue('Org');
  });
});
