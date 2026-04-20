'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useToast } from '@/components/ui/use-toast';
import type { UserRole } from '@/lib/database.types';
import { PersonalInfoStep } from './steps/personal-info-step';
import { ProfessionalInfoStep } from './steps/professional-info-step';
import { UploadCVStep } from './steps/upload-cv-step';

export type OnboardingData = {
  full_name: string;
  email: string;
  role: UserRole;
  institution_name: string;
  department: string;
  academic_level: string;
  field_of_study: string;
  bio: string;
};

interface Props {
  initialData?: Partial<OnboardingData>;
}

export function OnboardingFlow({ initialData }: Props) {
  const router = useRouter();
  const { toast } = useToast();
  const [currentStep, setCurrentStep] = useState(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [data, setData] = useState<OnboardingData>({
    full_name: initialData?.full_name ?? '',
    email: initialData?.email ?? '',
    role: initialData?.role ?? 'student',
    institution_name: initialData?.institution_name ?? '',
    department: initialData?.department ?? '',
    academic_level: initialData?.academic_level ?? '',
    field_of_study: initialData?.field_of_study ?? '',
    bio: initialData?.bio ?? '',
  });

  const updateData = (newData: Partial<OnboardingData>) => {
    setData((prev) => ({ ...prev, ...newData }));
  };

  const handleComplete = async () => {
    setIsSubmitting(true);

    try {
      const profileResponse = await fetch('/api/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });

      if (!profileResponse.ok) {
        let errorMessage = 'Failed to save profile';

        try {
          const errorData = await profileResponse.json();
          console.error('Profile API error:', errorData);
          errorMessage = errorData.details || errorData.message || errorData.error || errorMessage;
        } catch (parseError) {
          console.error('Failed to parse profile API error:', parseError);
        }

        throw new Error(errorMessage);
      }

      toast({
        description: 'Your Veridex profile is ready.',
      });

      router.push('/dashboard');
      router.refresh();
    } catch (error) {
      console.error('Error completing onboarding:', error);
      toast({
        description: error instanceof Error ? error.message : 'Something went wrong. Please try again.',
        variant: 'destructive',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="w-full max-w-2xl">
        {currentStep === 1 ? (
          <PersonalInfoStep data={data} updateData={updateData} onNext={() => setCurrentStep(2)} />
        ) : null}

        {currentStep === 2 ? (
          <ProfessionalInfoStep
            data={data}
            updateData={updateData}
            onBack={() => setCurrentStep(1)}
            onNext={() => setCurrentStep(3)}
          />
        ) : null}

        {currentStep === 3 ? (
          <UploadCVStep
            data={data}
            updateData={updateData}
            onBack={() => setCurrentStep(2)}
            onComplete={handleComplete}
            isSubmitting={isSubmitting}
          />
        ) : null}
      </div>
    </div>
  );
}
