// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { h, renderRollCall } from './rollcallHarness';

afterEach(cleanup);
it('confirms the selected approved row with 1 then Enter', async () => {
  renderRollCall();
  fireEvent.keyDown(window, { key: '1' });
  fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Enter' });
  await waitFor(() =>
    expect(h.actions.confirm.mutateAsync).toHaveBeenCalledExactlyOnceWith({
      id: 101,
    }),
  );
});
