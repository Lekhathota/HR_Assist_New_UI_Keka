import { clearToken, getToken, saveToken } from './api.js';

afterEach(() => { localStorage.clear(); sessionStorage.clear(); });

test('remembered sessions survive the browser session; others do not', () => {
  saveToken('long', true);
  expect(localStorage.getItem('session_token')).toBe('long');
  expect(sessionStorage.getItem('session_token')).toBeNull();
  expect(getToken()).toBe('long');

  saveToken('short', false);
  expect(localStorage.getItem('session_token')).toBeNull();
  expect(sessionStorage.getItem('session_token')).toBe('short');
  expect(getToken()).toBe('short');

  clearToken();
  expect(getToken()).toBe('');
});
