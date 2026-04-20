import { redirect } from 'next/navigation';
import { OnboardingFlow } from '@/components/onboarding/onboarding-flow';
import { createClient } from '@/utils/supabase/server';
import {
  buildBootstrapProfile,
  getBootstrapEmail,
  getBootstrapFullName,
  normalizeUserRole,
} from '@/lib/profile-bootstrap';

export default async function OnboardingPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect('/login');
  }

  const { data: profiles, error } = await supabase.from('profiles').select('id').eq('user_id', user.id).limit(1);

  if (error) {
    console.error('Error checking existing profile during onboarding:', error);
  }

  if (profiles?.[0]) {
    redirect('/dashboard');
  }

  if (!profiles?.[0]) {
    const { error: bootstrapError } = await supabase
      .from('profiles')
      .upsert(buildBootstrapProfile(user), { onConflict: 'user_id', ignoreDuplicates: true });

    if (!bootstrapError) {
      redirect('/dashboard');
    }

    console.error('Error bootstrapping profile during onboarding:', bootstrapError);
  }

  return (
    <OnboardingFlow
      initialData={{
        full_name: getBootstrapFullName(user),
        email: getBootstrapEmail(user),
        role: normalizeUserRole(user.user_metadata?.role),
      }}
    />
  );
}
