'use client';

import Image from 'next/image';
import { LoaderIcon } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { OnboardingData } from '../onboarding-flow';

interface Props {
  data: OnboardingData;
  updateData: (data: Partial<OnboardingData>) => void;
  onComplete: () => void;
  onBack: () => void;
  isSubmitting: boolean;
}

export function UploadCVStep({ data, updateData, onComplete, onBack, isSubmitting }: Props) {
  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    onComplete();
  };

  return (
    <form onSubmit={handleSubmit}>
      <Card className="border bg-card/80 backdrop-blur-[6px]">
        <CardHeader className="text-center pb-4">
          <div className="mb-4 flex justify-center">
            <Image src="/assets/icons/logo/veridex-icon.svg" alt="Veridex logo" width={60} height={60} />
          </div>
          <CardTitle className="text-[30px] leading-[36px] font-medium tracking-[-0.6px]">Finish Your Profile</CardTitle>
          <CardDescription className="mt-2 text-muted-foreground">Step 3 of 3: Add a short note and enter the workspace</CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          <div className="grid w-full items-center gap-1.5">
            <Label htmlFor="bio" className="text-muted-foreground leading-5">
              Short Bio or Notes
            </Label>
            <textarea
              id="bio"
              value={data.bio}
              onChange={(event) => updateData({ bio: event.target.value })}
              placeholder={
                data.role === 'teacher'
                  ? 'e.g., I teach oral communication and software engineering modules for second-year students.'
                  : 'e.g., I am preparing for oral exams in Java, algorithms, and software engineering.'
              }
              className="min-h-32 rounded-md border border-border bg-transparent px-3 py-2 text-sm outline-none ring-offset-background placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          <div className="rounded-lg bg-muted/50 p-4 text-sm text-muted-foreground">
            <p className="mb-1 font-medium">Profile summary</p>
            <p className="text-xs">
              You&apos;re joining Veridex as a {data.role}. We&apos;ll save this education profile and take you straight to the dashboard.
            </p>
          </div>

          <div className="mt-6 flex gap-3">
            <Button type="button" onClick={onBack} variant="outline" className="w-full" disabled={isSubmitting}>
              Back
            </Button>
            <Button type="submit" variant="secondary" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <LoaderIcon className="mr-2 h-4 w-4 animate-spin" />
                  Setting up...
                </>
              ) : (
                'Enter Veridex'
              )}
            </Button>
          </div>

          <div className="text-center">
            <button
              type="button"
              onClick={onComplete}
              className="text-sm text-muted-foreground underline hover:text-foreground"
              disabled={isSubmitting}
            >
              Finish without a bio
            </button>
          </div>
        </CardContent>
      </Card>
    </form>
  );
}
