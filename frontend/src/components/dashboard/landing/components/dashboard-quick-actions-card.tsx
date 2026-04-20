'use client';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { BookOpen, ClipboardCheck, GraduationCap, LoaderIcon, Settings } from 'lucide-react';
import { useEffect, useState } from 'react';
import { fetchExamContext } from '@/features/exams/lib/client';

export function DashboardQuickActionsCard() {
  const [context, setContext] = useState<Awaited<ReturnType<typeof fetchExamContext>> | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const loadContext = async () => {
      try {
        const response = await fetchExamContext();
        setContext(response);
      } catch (error) {
        console.error('Error fetching quick actions context:', error);
      } finally {
        setIsLoading(false);
      }
    };

    void loadContext();
  }, []);

  const role = context?.role ?? null;
  const isTeacher = role === 'teacher' || role === 'admin';

  return (
    <Card>
      <CardHeader>
        <CardTitle>Quick Actions</CardTitle>
        <CardDescription>Jump into the new Veridex exam workspace</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <Button asChild variant="secondary" className="h-auto w-full flex-col gap-2 py-4">
            <Link href={isTeacher ? '/dashboard/exams#create-exam' : '/dashboard/exams#join-exam'}>
              {isLoading ? <LoaderIcon className="h-6 w-6 animate-spin" /> : <GraduationCap className="h-6 w-6" />}
              <span className="font-medium">{isTeacher ? 'Create Exam' : 'Join Exam'}</span>
              <span className="text-xs text-muted-foreground">
                {isTeacher ? 'Publish a new oral or written exam' : 'Enroll with a teacher join code'}
              </span>
            </Link>
          </Button>

          <Button asChild variant="outline" className="h-auto w-full flex-col gap-2 py-4">
            <Link href="/dashboard/exams">
              <BookOpen className="h-6 w-6" />
              <span className="font-medium">{isTeacher ? 'Manage Exams' : 'My Exams'}</span>
              <span className="text-xs text-muted-foreground">
                {isTeacher ? 'Open exam detail pages and attempts' : 'View joined exams and private attempts'}
              </span>
            </Link>
          </Button>

          <Button asChild variant="outline" className="h-auto w-full flex-col gap-2 py-4">
            <Link href={isTeacher ? '/dashboard/evaluations' : '/dashboard/evaluations'}>
              <ClipboardCheck className="h-6 w-6" />
              <span className="font-medium">{isTeacher ? 'Live Evaluations' : 'My Results'}</span>
              <span className="text-xs text-muted-foreground">
                {isTeacher
                  ? 'Watch scores stream in and handle contestations'
                  : 'Track evaluations and contest libre grades'}
              </span>
            </Link>
          </Button>

          <Button asChild variant="outline" className="h-auto w-full flex-col gap-2 py-4">
            <Link href="/dashboard/settings">
              <Settings className="h-6 w-6" />
              <span className="font-medium">Settings</span>
              <span className="text-xs text-muted-foreground">Update your account and profile</span>
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
