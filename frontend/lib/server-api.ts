import { headers } from 'next/headers';

export async function getServerApiBaseUrl(): Promise<string> {
  const headerStore = await headers();
  const host = headerStore.get('x-forwarded-host') ?? headerStore.get('host');
  const proto = headerStore.get('x-forwarded-proto') ?? 'https';

  if (host) {
    return `${proto}://${host}`;
  }

  if (process.env.API_URL) {
    return process.env.API_URL;
  }

  if (process.env.VERCEL_URL) {
    return `https://${process.env.VERCEL_URL}`;
  }

  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }

  if (process.env.NODE_ENV === 'development') {
    return 'http://127.0.0.1:8000';
  }

  throw new Error('Unable to resolve server API base URL for production runtime.');
}