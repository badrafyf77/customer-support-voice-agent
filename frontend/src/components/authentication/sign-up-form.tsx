'use client';

import Image from 'next/image';
import { Button } from '@/components/ui/button';
import { useState } from 'react';
import { AuthenticationForm } from '@/components/authentication/authentication-form';
import { signup } from '@/app/signup/actions';
import { useToast } from '@/components/ui/use-toast';
import type { UserRole } from '@/lib/database.types';
import { GraduationCap, School2 } from 'lucide-react';

export function SignupForm() {
  const { toast } = useToast();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<UserRole>('student');

  async function handleSignup() {
    const result = await signup({ email, password, role });

    if (result?.error) {
      toast({
        description: result.message || 'Something went wrong. Please try again.',
        variant: 'destructive',
      });
    }
  }

  return (
    <form action={'#'} className={'px-6 md:px-16 pb-6 py-8 gap-6 flex flex-col items-center justify-center'}>
      <Image src={'/assets/icons/logo/veridex-icon.svg'} alt={'Veridex'} width={80} height={80} />
      <div className={'text-[30px] leading-[36px] font-medium tracking-[-0.6px] text-center'}>Create an account</div>
      <div className="grid w-full gap-3">
        <p className="text-sm font-medium text-muted-foreground">I am joining Veridex as a</p>
        <div className="grid gap-3 md:grid-cols-2">
          <button
            type="button"
            onClick={() => setRole('student')}
            className={`rounded-lg border px-4 py-4 text-left transition-colors ${
              role === 'student' ? 'border-primary bg-primary/10' : 'border-border hover:border-primary/50'
            }`}
          >
            <div className="mb-2 flex items-center gap-2 font-medium">
              <GraduationCap className="h-4 w-4" />
              Student
            </div>
            <p className="text-sm text-muted-foreground">Join exams with a code and take private oral or written attempts.</p>
          </button>

          <button
            type="button"
            onClick={() => setRole('teacher')}
            className={`rounded-lg border px-4 py-4 text-left transition-colors ${
              role === 'teacher' ? 'border-primary bg-primary/10' : 'border-border hover:border-primary/50'
            }`}
          >
            <div className="mb-2 flex items-center gap-2 font-medium">
              <School2 className="h-4 w-4" />
              Teacher
            </div>
            <p className="text-sm text-muted-foreground">Create exams, share join codes, and review student attempts.</p>
          </button>
        </div>
      </div>
      <AuthenticationForm
        email={email}
        onEmailChange={(email) => setEmail(email)}
        password={password}
        onPasswordChange={(password) => setPassword(password)}
      />
      <Button formAction={handleSignup} type={'submit'} variant={'secondary'} className={'w-full'}>
        Sign up
      </Button>
    </form>
  );
}
