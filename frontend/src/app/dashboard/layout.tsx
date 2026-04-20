import { ReactNode } from 'react';
import { DashboardLayout } from '@/components/dashboard/layout/dashboard-layout';
import { createClient } from '@/utils/supabase/server';
import { redirect } from 'next/navigation';
import { buildBootstrapProfile } from '@/lib/profile-bootstrap';

interface Props {
  children: ReactNode;
}

function isNonFatalProfileBootstrapError(error: unknown) {
  if (!error || typeof error !== 'object') {
    return false;
  }

  const payload = error as Record<string, unknown>;
  const code = typeof payload.code === 'string' ? payload.code : '';
  const message = typeof payload.message === 'string' ? payload.message : '';
  const details = typeof payload.details === 'string' ? payload.details : '';
  const hint = typeof payload.hint === 'string' ? payload.hint : '';
  const combined = `${message} ${details} ${hint}`.toLowerCase();

  return (
    code === 'PGRST205' ||
    code === '42P01' ||
    code === '42501' ||
    !code ||
    (combined.includes('profiles') &&
      (combined.includes('could not find the table') ||
        combined.includes('does not exist') ||
        combined.includes('permission denied')))
  );
}

export default async function Layout({ children }: Props) {
  const sessionSupabase = await createClient();
  const { data } = await sessionSupabase.auth.getUser();
  const user = data.user;

  if (!user) {
    redirect('/login');
  }

  const { data: profiles, error: profileLookupError } = await sessionSupabase
    .from('profiles')
    .select('id')
    .eq('user_id', user.id)
    .limit(1);

  if (profileLookupError && !isNonFatalProfileBootstrapError(profileLookupError)) {
    console.error('Error checking onboarding status:', profileLookupError);
  }

  if (!profileLookupError && !profiles?.[0]) {
    const { error: bootstrapError } = await sessionSupabase
      .from('profiles')
      .upsert(buildBootstrapProfile(user), { onConflict: 'user_id', ignoreDuplicates: true });

    if (bootstrapError && !isNonFatalProfileBootstrapError(bootstrapError)) {
      console.error('Error bootstrapping profile during dashboard access:', bootstrapError);
    }
  }

  return <DashboardLayout>{children}</DashboardLayout>;
}
