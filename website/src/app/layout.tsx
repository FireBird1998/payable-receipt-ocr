import type { Metadata } from 'next';
import { IBM_Plex_Mono, Source_Sans_3 } from 'next/font/google';
import { Provider } from '@/components/provider';
import { appDescription, appName, repoUrl, siteUrl } from '@/lib/shared';
import './global.css';

const sans = Source_Sans_3({
  subsets: ['latin'],
  variable: '--font-sans',
});

const mono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-mono',
});

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: appName,
    template: `%s · ${appName}`,
  },
  description: appDescription,
  applicationName: appName,
  alternates: {
    canonical: '/',
  },
  openGraph: {
    title: appName,
    description: appDescription,
    url: siteUrl,
    siteName: appName,
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: appName,
    description: appDescription,
  },
  robots: {
    index: true,
    follow: true,
  },
  category: 'technology',
  other: {
    'source-code': repoUrl,
  },
};

export default function Layout({ children }: LayoutProps<'/'>) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <body className="flex min-h-screen flex-col">
        <Provider>{children}</Provider>
      </body>
    </html>
  );
}
