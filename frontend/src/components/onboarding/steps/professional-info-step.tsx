'use client';

import Image from 'next/image';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { OnboardingData } from '../onboarding-flow';

interface Props {
  data: OnboardingData;
  updateData: (data: Partial<OnboardingData>) => void;
  onNext: () => void;
  onBack: () => void;
}

export function ProfessionalInfoStep({ data, updateData, onNext, onBack }: Props) {
  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    onNext();
  };

  return (
    <form onSubmit={handleSubmit}>
      <Card className="border bg-card/80 backdrop-blur-[6px]">
        <CardHeader className="text-center pb-4">
          <div className="mb-4 flex justify-center">
            <Image src="/assets/icons/logo/veridex-icon.svg" alt="Veridex logo" width={60} height={60} />
          </div>
          <CardTitle className="text-[30px] leading-[36px] font-medium tracking-[-0.6px]">Your Academic Context</CardTitle>
          <CardDescription className="mt-2 text-muted-foreground">Step 2 of 3: Tell Veridex where this profile fits</CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          <div className="grid w-full items-center gap-1.5">
            <Label htmlFor="institution_name" className="text-muted-foreground leading-5">
              Institution
            </Label>
            <Input
              id="institution_name"
              type="text"
              placeholder={data.role === 'teacher' ? 'e.g., ENSET Mohammedia' : 'e.g., ENSA Casablanca'}
              value={data.institution_name}
              onChange={(event) => updateData({ institution_name: event.target.value })}
              className="border-border rounded-xs"
            />
          </div>

          <div className="grid w-full items-center gap-1.5">
            <Label htmlFor="department" className="text-muted-foreground leading-5">
              {data.role === 'teacher' ? 'Department or Module' : 'Department or Track'}
            </Label>
            <Input
              id="department"
              type="text"
              placeholder={data.role === 'teacher' ? 'e.g., Computer Science' : 'e.g., Software Engineering'}
              value={data.department}
              onChange={(event) => updateData({ department: event.target.value })}
              className="border-border rounded-xs"
            />
          </div>

          <div className="grid w-full items-center gap-1.5">
            <Label htmlFor="academic_level" className="text-muted-foreground leading-5">
              {data.role === 'teacher' ? 'Teaching Level' : 'Academic Level'}
            </Label>
            <Input
              id="academic_level"
              type="text"
              placeholder={data.role === 'teacher' ? 'e.g., Undergraduate, Master' : 'e.g., 2nd Year, Master 1'}
              value={data.academic_level}
              onChange={(event) => updateData({ academic_level: event.target.value })}
              className="border-border rounded-xs"
            />
          </div>

          <div className="grid w-full items-center gap-1.5">
            <Label htmlFor="field_of_study" className="text-muted-foreground leading-5">
              {data.role === 'teacher' ? 'Subject Area' : 'Field of Study'}
            </Label>
            <Input
              id="field_of_study"
              type="text"
              placeholder={data.role === 'teacher' ? 'e.g., Oral Communication, Java, Networks' : 'e.g., Computer Science'}
              value={data.field_of_study}
              onChange={(event) => updateData({ field_of_study: event.target.value })}
              className="border-border rounded-xs"
            />
          </div>

          <div className="mt-6 flex gap-3">
            <Button type="button" onClick={onBack} variant="outline" className="w-full">
              Back
            </Button>
            <Button type="submit" variant="secondary" className="w-full">
              Continue
            </Button>
          </div>
        </CardContent>
      </Card>
    </form>
  );
}
