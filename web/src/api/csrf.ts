export const CSRF_COOKIE_NAME =
  import.meta.env.VITE_CSRF_COOKIE_NAME?.trim() || 'tradingagents_csrf';

export function readCookie(name: string): string | null {
  const escaped = name.replace(/[.$?*|{}()[\]\\/+^]/g, '\\$&');
  const match = document.cookie.match(new RegExp(`(?:^|; )${escaped}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export function readCsrfToken(): string | null {
  return readCookie(CSRF_COOKIE_NAME);
}
