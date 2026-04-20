'use client';

import Image from 'next/image';
import { GraduationCap, School2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { OnboardingData } from '../onboarding-flow';

interface Props {
  data: OnboardingData;
  updateData: (data: Partial<OnboardingData>) => void;
  onNext: () => void;
}

export function PersonalInfoStep({ data, updateData, onNext }: Props) {
  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();

    if (!data.full_name || !data.email || !data.role) {
      alert('Please complete your name, email, and role.');
      return;
    }

    onNext();
  };

  return (
    <form onSubmit={handleSubmit}>
      <Card className="border bg-card/80 backdrop-blur-[6px]">
        <CardHeader className="text-center pb-4">
          <div className="mb-4 flex justify-center">
            <Image src="/assets/icons/logo/veridex-icon.svg" alt="Veridex logo" width={60} height={60} />
          </div>
          <CardTitle className="text-[30px] leading-[36px] font-medium tracking-[-0.6px]">Welcome to Veridex</CardTitle>
          <CardDescription className="mt-2 text-muted-foreground">Step 1 of 3: Choose your role and basic details</CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          <div className="grid gap-3">
            <Label className="text-muted-foreground leading-5">
              I&apos;m joining as a <span className="text-destructive">*</span>
            </Label>
            <div className="grid gap-3 md:grid-cols-2">
              <button
                type="button"
                onClick={() => updateData({ role: 'student' })}
                className={`rounded-lg border px-4 py-4 text-left transition-colors ${
                  data.role === 'student' ? 'border-primary bg-primary/10' : 'border-border hover:border-primary/50'
                }`}
              >
                <div className="mb-2 flex items-center gap-2 font-medium">
                  <GraduationCap className="h-4 w-4" />
                  Student
                </div>
                <p className="text-sm text-muted-foreground">Join teacher exams, complete private attempts, and review your feedback.</p>
              </button>

              <button
                type="button"
                onClick={() => updateData({ role: 'teacher' })}
                className={`rounded-lg border px-4 py-4 text-left transition-colors ${
                  data.role === 'teacher' ? 'border-primary bg-primary/10' : 'border-border hover:border-primary/50'
                }`}
              >
                <div className="mb-2 flex items-center gap-2 font-medium">
                  <School2 className="h-4 w-4" />
                  Teacher
                </div>
                <p className="text-sm text-muted-foreground">Create exams, publish join codes, and review class results.</p>
              </button>
            </div>
          </div>

          <div className="grid w-full items-center gap-1.5">
            <Label htmlFor="full_name" className="text-muted-foreground leading-5">
              Full Name <span className="text-destructive">*</span>
            </Label>
            <Input
              id="full_name"
              type="text"
              placeholder="John Doe"
              value={data.full_name}
              onChange={(event) => updateData({ full_name: event.target.value })}
              className="border-border rounded-xs"
              required
            />
          </div>

          <div className="grid w-full items-center gap-1.5">
            <Label htmlFor="email" className="text-muted-foreground leading-5">
              Email <span className="text-destructive">*</span>
            </Label>
            <Input
              id="email"
              type="email"
              placeholder="john@example.com"
              value={data.email}
              onChange={(event) => updateData({ email: event.target.value })}
              className="border-border rounded-xs"
              required
            />
          </div>

          <Button type="submit" variant="secondary" className="mt-6 w-full">
            Continue
          </Button>
        </CardContent>
      </Card>
    </form>
  );
}
