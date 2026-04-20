'use client';

import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useEffect, useState } from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import { fetchExamContext } from '@/features/exams/lib/client';
import { getRoleLabel } from '@/features/exams/lib/formatters';

export function DashboardWelcomeCard() {
  const [context, setContext] = useState<Awaited<ReturnType<typeof fetchExamContext>> | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const loadContext = async () => {
      try {
        const response = await fetchExamContext();
        setContext(response);
      } catch (error) {
        console.error('Error fetching exam context:', error);
      } finally {
        setIsLoading(false);
      }
    };

    void loadContext();
  }, []);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-64 mt-2" />
        </CardHeader>
      </Card>
    );
  }

  const firstName = context?.context.profile?.full_name?.split(' ')[0] || 'there';
  const role = context?.role ?? null;
  const description = !context?.hasProfile
    ? 'Veridex is ready. Create your profile row and assign a teacher or student role to unlock the exam workspace.'
    : role === 'teacher' || role === 'admin'
      ? 'Build oral and written exams, publish join codes, and review private student attempts from one workspace.'
      : 'Join your teacher’s exam, start a private attempt, and review feedback without sharing your session with other students.';

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-2xl">Welcome back, {firstName}</CardTitle>
        <CardDescription className="text-base">{description}</CardDescription>
        {role ? <CardDescription>Your active Veridex role is {getRoleLabel(role).toLowerCase()}.</CardDescription> : null}
      </CardHeader>
    </Card>
  );
}
