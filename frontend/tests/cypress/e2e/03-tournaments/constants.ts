export const dateYYYYMMDD = (() => {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
})();
export const date2YYYYMMDD = (() => {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 2).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
})();
export const description = 'Created by Cypress end-to-end test';
export const thisName = `Cypress Tournament ${dateYYYYMMDD}`;
export const editedName = `Cypress Tournament Edited ${date2YYYYMMDD}`;
export const completedBracketTest = `Completed Bracket Test`;
