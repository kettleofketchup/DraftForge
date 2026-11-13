export const isCsrfCookie = (name: string): boolean => name === 'csrftoken';
export const isSessionCookie = (name: string): boolean => name === 'sessionid';
