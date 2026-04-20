'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { BookOpen, Clock3, ExternalLink, GraduationCap } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { fetchExamContext, fetchExams } from '@/features/exams/lib/client';
import { formatDateTime, getExamModeLabel, getExamStatusBadgeVariant, isExamOpen } from '@/features/exams/lib/formatters';
import type { Exam } from '@/features/exams/types';

export function DashboardRecentExamsCard() {
  const [context, setContext] = useState<Awaited<ReturnType<typeof fetchExamContext>> | null>(null);
  const [exams, setExams] = useState<Exam[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const loadRecentExams = async () => {
      try {
        const nextContext = await fetchExamContext();
        setContext(nextContext);

        if (!nextContext.hasProfile || !nextContext.role) {
          return;
        }

        const response = await fetchExams({ limit: 3 });
        setExams(response.exams || []);
      } catch (error) {
        console.error('Error fetching recent exams:', error);
      } finally {
        setIsLoading(false);
      }
    };

    void loadRecentExams();
  }, []);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Recent Exams</CardTitle>
          <CardDescription>Latest Veridex activity</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {[1, 2, 3].map((item) => (
            <div key={item} className="flex items-center gap-4">
              <Skeleton className="h-12 w-12 rounded" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-3 w-2/3" />
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    );
  }

  if (!context?.hasProfile || !context.role) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Veridex Exams</CardTitle>
          <CardDescription>The new exam workspace is ready for profile activation.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Create your profile row and assign a teacher or student role to start seeing exam activity here.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (exams.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{context.role === 'student' ? 'Joined Exams' : 'Recent Exams'}</CardTitle>
          <CardDescription>{context.role === 'student' ? 'Exams you can open privately' : 'Teacher-owned exams you created recently'}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="py-8 text-center">
            <p className="mb-4 text-muted-foreground">
              {context.role === 'student' ? 'No exams joined yet' : 'No exams created yet'}
            </p>
            <Button asChild variant="secondary">
              <Link href="/dashboard/exams">
                {context.role === 'student' ? 'Open Exam Workspace' : 'Create Your First Exam'}
              </Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-4">
          <div>
            <CardTitle>{context.role === 'student' ? 'Joined Exams' : 'Recent Exams'}</CardTitle>
            <CardDescription>
              {context.role === 'student'
                ? 'Private exam sessions you are enrolled in'
                : 'Latest shared exams you can open for attempt review'}
            </CardDescription>
          </div>
          <Button asChild variant="ghost" size="sm">
            <Link href="/dashboard/exams">View All</Link>
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {exams.map((exam) => (
          <div key={exam.id} className="rounded-lg border p-4 transition-colors hover:bg-accent/50">
            <div className="flex items-start gap-4">
              <div className="rounded bg-primary/10 p-2">
                {context.role === 'student' ? (
                  <GraduationCap className="h-5 w-5 text-primary" />
                ) : (
                  <BookOpen className="h-5 w-5 text-primary" />
                )}
              </div>

              <div className="min-w-0 flex-1 space-y-3">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div className="min-w-0">
                    <h4 className="truncate font-medium">{exam.title}</h4>
                    <p className="truncate text-sm text-muted-foreground">{exam.subject}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant={getExamStatusBadgeVariant(exam.status)}>{exam.status}</Badge>
                    <Badge variant="outline">{getExamModeLabel(exam.exam_mode)}</Badge>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
                  <div className="flex items-center gap-1.5">
                    <Clock3 className="h-3.5 w-3.5" />
                    {exam.start_at ? formatDateTime(exam.start_at) : formatDateTime(exam.created_at)}
                  </div>
                  <div>{isExamOpen(exam) ? 'Open now' : 'Outside active window'}</div>
                  {context.role !== 'student' ? <div>Join code: {exam.join_code}</div> : null}
                </div>
              </div>

              <Button asChild size="sm" variant="outline">
                <Link href={`/dashboard/exams/${exam.id}`}>
                  <ExternalLink className="h-4 w-4" />
                </Link>
              </Button>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
