'use server';

import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';
import { createClient } from '@/utils/supabase/server';
import type { UserRole } from '@/lib/database.types';

interface FormData {
  email: string;
  password: string;
  role: UserRole;
}

export async function signup(data: FormData) {
  const supabase = await createClient();

  const { data: signUpData, error } = await supabase.auth.signUp({
    email: data.email,
    password: data.password,
    options: {
      data: {
        role: data.role,
      },
    },
  });

  if (error) {
    return { error: true, message: error.message };
  }

  if (!signUpData.session) {
    return {
      error: true,
      message: 'Signup succeeded but no session was created. Check your Supabase email confirmation settings.',
    };
  }

  revalidatePath('/', 'layout');
  redirect('/onboarding');
}
