// ***********************************************************
// This example support/component.ts is processed and
// loaded automatically before your component test files.
//
// This is a great place to put global configuration and
// behavior that modifies Cypress.
//
// You can change the location of this file or turn off
// automatically serving support files with the
// 'supportFile' configuration option.
//
// You can read more here:
// https://on.cypress.io/configuration
// ***********************************************************

// Import commands.js using ES2015 syntax:
import './commands';

// Mount command for React components
//cypress/support/component.ts
import { mount } from 'cypress/react';
declare global {
  namespace Cypress {
    interface Chainable {
      mount: typeof mount;
    }
  }
}
Cypress.Commands.add('mount', (jsx, options) => {
  assertDarkThemeAttached();
  const result = mount(jsx, options);
  result.then(
    () => (parent.window.document.querySelector('iframe')!.style.display = ''),
  );
  return result;
});

const assertDarkThemeAttached = () => {
  const parentHead = Cypress.$(parent.window.document.head);
  if (parentHead.find('#cypress-dark').length > 0) return;
  parentHead.append(
    `<style type="text/css" id="cypress-dark">\n${style}</style>`,
  );
  parent.window.eval(`
    const observer = new MutationObserver(() => {
        const iframe = document.querySelector('iframe')
        if(!iframe) return;
        const cyRoot = iframe.contentDocument.body.querySelector('[data-cy-root]')
        if(!cyRoot) iframe.style.display = 'none'
        // iframe.style.display = cyRoot ? '' : 'none'
    })
    observer.observe(document.body, { attributes: true, childList: true, subtree: true })
    `);
};
//wrapper for syntax highlighting
const css = (val: any) => val;
const style = css`
  @media (prefers-color-scheme: dark) {
    :root {
      --active-color: #cccccc;
      --background: #222426;
    }
    html,
    body,
    #spec-filter,
    .h-full,
    .flex,
    .spec-container,
    .bg-white {
      background-color: var(--background) !important;
      color: var(--active-color) !important;
    }
  }
`;
