import '../styles/globals.css';
import '../styles/layout.css';
import { ReactNode } from 'react';
import type { Metadata } from 'next';
import { Toaster } from '@/components/ui/toaster';

export const metadata: Metadata = {
  title: 'Veridex',
  description: 'Run oral and written exams with realtime AI voice assessment, transcripts, and rubric-based feedback.',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="en" className={'min-h-full dark scroll-smooth'}>
      <body className="min-h-full">
        {children}
        <Toaster />
      </body>
    </html>
  );
}
