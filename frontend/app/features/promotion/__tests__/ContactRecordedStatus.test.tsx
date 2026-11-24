// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { I18nextProvider } from 'react-i18next';
import { describe, expect, it } from 'vitest';
import { createI18nInstance } from '~/i18n/config';
import { ContactRecordedStatus } from '../ContactRecordedStatus';
import type { LastMessaged } from '../schemas';
import { SFG_CONTACT } from './fixtures';

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <I18nextProvider i18n={createI18nInstance('en')}>
      {children}
    </I18nextProvider>
  );
}

const local: LastMessaged = {
  send_id: 77,
  by: 'Promoter Pat',
  sent_at: '2026-11-24T10:00:00Z',
  can_undo: true,
};

describe('ContactRecordedStatus', () => {
  it('renders nothing without any recorded contact', () => {
    const { container } = render(
      <ContactRecordedStatus
        externalContact={null}
        localLastMessaged={null}
        testId="42"
      />,
      { wrapper: Wrapper },
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows an imported contact as a read-only checked status with time and delivery disclaimer', () => {
    render(
      <ContactRecordedStatus
        externalContact={SFG_CONTACT}
        localLastMessaged={null}
        testId="42"
      />,
      { wrapper: Wrapper },
    );
    const tick = screen.getByRole('checkbox', {
      name: 'Contact recorded in SFG',
    });
    expect(tick).toHaveAttribute('aria-checked', 'true');
    expect(tick).toHaveAttribute('aria-readonly', 'true');
    expect(tick).toHaveAccessibleDescription(/Delivery not verified/);
    const status = screen.getByTestId('promo-external-contact-42');
    expect(status).toHaveTextContent('Contact recorded in SFG');
    expect(status).toHaveTextContent('Delivery not verified');
    const time = status.querySelector('time');
    expect(time).toHaveAttribute('datetime', SFG_CONTACT.recorded_at);
    expect(screen.queryByTestId('promo-last-messaged-42')).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('keeps the read-only tick checked when clicked or toggled from the keyboard', () => {
    render(
      <ContactRecordedStatus
        externalContact={SFG_CONTACT}
        localLastMessaged={null}
        testId="42"
      />,
      { wrapper: Wrapper },
    );
    const tick = screen.getByRole('checkbox', {
      name: 'Contact recorded in SFG',
    });
    tick.focus();
    expect(tick).toHaveFocus();
    fireEvent.keyDown(tick, { key: ' ' });
    fireEvent.click(tick);
    expect(tick).toHaveAttribute('aria-checked', 'true');
  });

  it('shows local and external history separately', () => {
    render(
      <ContactRecordedStatus
        externalContact={SFG_CONTACT}
        localLastMessaged={local}
        testId="42"
      />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId('promo-last-messaged-42')).toHaveTextContent(
      'Messaged by Promoter Pat',
    );
    expect(screen.getByTestId('promo-external-contact-42')).toHaveTextContent(
      'Contact recorded in SFG',
    );
  });

  it('shows only the local line for a local-only send', () => {
    render(
      <ContactRecordedStatus
        externalContact={null}
        localLastMessaged={{ ...local, by: null }}
        testId="42"
      />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId('promo-last-messaged-42')).toHaveTextContent(
      'Messaged by someone',
    );
    expect(screen.queryByRole('checkbox')).toBeNull();
  });
});
