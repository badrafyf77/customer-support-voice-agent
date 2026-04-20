'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  ClipboardCheck,
  ExternalLink,
  FileText,
  LoaderIcon,
  PlayCircle,
  ShieldCheck,
  Users,
} from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { fetchExamAttempts, fetchExamContext, fetchExamDetail, startExamAttempt } from '../lib/client';
import {
  countCompletedAttempts,
  formatDateTime,
  formatDurationMinutes,
  getAttemptStatusBadgeVariant,
  getExamModeLabel,
  getExamStatusBadgeVariant,
  getScoreBadgeVariant,
  isExamOpen,
} from '../lib/formatters';
import type { ExamAttempt, ExamAttemptsResponse, ExamDetailResponse, ExamRubricCriterion, UserRole } from '../types';

function isTeacherRole(role: UserRole | null) {
  return role === 'teacher' || role === 'admin';
}

function ExamDetailSkeleton() {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <Skeleton className="h-7 w-72" />
          <Skeleton className="h-4 w-full max-w-2xl" />
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-4">
          {[1, 2, 3, 4].map((item) => (
            <Skeleton key={item} className="h-24 w-full" />
          ))}
        </CardContent>
      </Card>

      {[1, 2].map((item) => (
        <Card key={item}>
          <CardHeader>
            <Skeleton className="h-6 w-48" />
          </CardHeader>
          <CardContent className="space-y-4">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function ScheduleText({ startAt, endAt }: { startAt: string | null; endAt: string | null }) {
  if (!startAt && !endAt) {
    return <span>Available immediately after publishing</span>;
  }

  if (startAt && !endAt) {
    return <span>Opens {formatDateTime(startAt)}</span>;
  }

  if (!startAt && endAt) {
    return <span>Closes {formatDateTime(endAt)}</span>;
  }

  return (
    <span>
      {formatDateTime(startAt)} to {formatDateTime(endAt)}
    </span>
  );
}

function RubricCriteriaList({ criteria }: { criteria: ExamRubricCriterion[] }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {criteria.map((criterion) => (
        <Card key={criterion.id}>
          <CardHeader className="pb-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle className="text-base">{criterion.criterion_label}</CardTitle>
                <CardDescription className="mt-1">
                  {criterion.description || 'Default Veridex scoring dimension'}
                </CardDescription>
              </div>
              <Badge variant="outline">{criterion.weight}%</Badge>
            </div>
          </CardHeader>
          <CardContent className="pt-0 text-sm text-muted-foreground">
            Score range: {criterion.score_min} to {criterion.score_max}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function StudentAttemptCards({ attempts, hideResults }: { attempts: ExamAttempt[]; hideResults: boolean }) {
  if (attempts.length === 0) {
    return (
      <Card>
        <CardContent className="py-10 text-center">
          <FileText className="mx-auto mb-4 h-10 w-10 text-muted-foreground" />
          <p className="font-medium">No attempts yet</p>
          <p className="mt-2 text-sm text-muted-foreground">Start your first private attempt when the exam is open.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {attempts.map((attempt) => (
        <Card key={attempt.id}>
          <CardContent className="flex flex-col gap-4 p-6 md:flex-row md:items-center md:justify-between">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-lg font-semibold">Attempt {attempt.attempt_number}</h3>
                <Badge variant={getAttemptStatusBadgeVariant(attempt.status)}>{attempt.status}</Badge>
                {attempt.overall_score != null && !hideResults ? (
                  <Badge variant={getScoreBadgeVariant(attempt.overall_score)}>{attempt.overall_score}/100</Badge>
                ) : null}
              </div>

              <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
                <span>Started {formatDateTime(attempt.started_at)}</span>
                <span>{attempt.ended_at ? `Ended ${formatDateTime(attempt.ended_at)}` : 'Still in progress'}</span>
              </div>

              {hideResults && attempt.status === 'evaluated' ? (
                <p className="text-sm text-muted-foreground">
                  This attempt has been evaluated, but results are hidden until the teacher releases them.
                </p>
              ) : null}
            </div>

            <Button asChild variant="outline">
              <Link href={`/dashboard/exams/attempts/${attempt.id}`}>
                Open attempt
                <ExternalLink className="ml-2 h-4 w-4" />
              </Link>
            </Button>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function TeacherAttemptsTable({ attemptsResponse }: { attemptsResponse: ExamAttemptsResponse }) {
  if (attemptsResponse.attempts.length === 0) {
    return (
      <Card>
        <CardContent className="py-10 text-center">
          <Users className="mx-auto mb-4 h-10 w-10 text-muted-foreground" />
          <p className="font-medium">No student attempts yet</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Once students start their private attempts, they will appear here for review and evaluation.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Student Attempts</CardTitle>
        <CardDescription>Each row below is a private student attempt inside this shared exam.</CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Student</TableHead>
              <TableHead>Attempt</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Score</TableHead>
              <TableHead>Submitted</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {attemptsResponse.attempts.map((attempt) => {
              const profile = attemptsResponse.profilesByUserId[attempt.student_user_id];
              return (
                <TableRow key={attempt.id}>
                  <TableCell>
                    <div>
                      <p className="font-medium">{profile?.full_name || 'Unknown student'}</p>
                      <p className="text-xs text-muted-foreground">{profile?.email || attempt.student_user_id}</p>
                    </div>
                  </TableCell>
                  <TableCell>#{attempt.attempt_number}</TableCell>
                  <TableCell>
                    <Badge variant={getAttemptStatusBadgeVariant(attempt.status)}>{attempt.status}</Badge>
                  </TableCell>
                  <TableCell>
                    {attempt.overall_score != null ? (
                      <Badge variant={getScoreBadgeVariant(attempt.overall_score)}>{attempt.overall_score}/100</Badge>
                    ) : (
                      <span className="text-sm text-muted-foreground">Pending</span>
                    )}
                  </TableCell>
                  <TableCell>{attempt.submitted_at ? formatDateTime(attempt.submitted_at) : 'Not submitted'}</TableCell>
                  <TableCell className="text-right">
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/dashboard/exams/attempts/${attempt.id}`}>
                        Review
                        <ArrowRight className="ml-2 h-4 w-4" />
                      </Link>
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

export function ExamDetail({ examId }: { examId: string }) {
  const router = useRouter();
  const [context, setContext] = useState<Awaited<ReturnType<typeof fetchExamContext>> | null>(null);
  const [detail, setDetail] = useState<ExamDetailResponse | null>(null);
  const [attemptsResponse, setAttemptsResponse] = useState<ExamAttemptsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isStartingAttempt, setIsStartingAttempt] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const loadDetail = useCallback(async () => {
    setErrorMessage(null);

    const nextContext = await fetchExamContext();
    setContext(nextContext);

    if (!nextContext.hasProfile || !nextContext.role) {
      setDetail(null);
      setAttemptsResponse(null);
      return;
    }

    const nextDetail = await fetchExamDetail(examId);
    setDetail(nextDetail);

    if (isTeacherRole(nextContext.role) && nextContext.context.user_id === nextDetail.exam.teacher_user_id) {
      const nextAttemptsResponse = await fetchExamAttempts(examId, { limit: 50 });
      setAttemptsResponse(nextAttemptsResponse);
      return;
    }

    setAttemptsResponse(null);
  }, [examId]);

  useEffect(() => {
    const initialize = async () => {
      try {
        await loadDetail();
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : 'Unable to load this exam.');
      } finally {
        setIsLoading(false);
      }
    };

    void initialize();
  }, [loadDetail]);

  const handleStartAttempt = async () => {
    if (!detail) {
      return;
    }

    setIsStartingAttempt(true);
    setActionMessage(null);
    setErrorMessage(null);

    try {
      const response = await startExamAttempt(detail.exam.id, { reuseInProgressAttempt: true });
      setActionMessage(response.message);
      if (response.exam.exam_mode === 'oral') {
        router.push(`/dashboard/exams/attempts/${response.attempt.id}/oral`);
      } else {
        router.push(`/dashboard/exams/attempts/${response.attempt.id}`);
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to start an attempt.');
    } finally {
      setIsStartingAttempt(false);
    }
  };

  if (isLoading) {
    return <ExamDetailSkeleton />;
  }

  if (errorMessage && !detail) {
    return (
      <Card>
        <CardContent className="py-10">
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Exam not available</AlertTitle>
            <AlertDescription>{errorMessage}</AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  if (!detail || !context?.role) {
    return (
      <Card>
        <CardContent className="py-10">
          <Alert>
            <ShieldCheck className="h-4 w-4" />
            <AlertTitle>Profile required</AlertTitle>
            <AlertDescription>Complete the new exam profile flow before opening this exam.</AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  const exam = detail.exam;
  const isTeacherOwner = isTeacherRole(context.role) && context.context.user_id === exam.teacher_user_id;
  const isStudentViewer = context.role === 'student';
  const openNow = isExamOpen(exam);
  const currentAttempt = detail.attempts.find((attempt) => attempt.status === 'in_progress');
  const canStartAttempt =
    isStudentViewer &&
    detail.enrollment?.status !== 'revoked' &&
    (currentAttempt != null || (openNow && detail.attempts.length < exam.max_attempts_per_student));
  const shouldHideStudentResults = isStudentViewer && !exam.show_results_immediately;
  const completedAttempts = countCompletedAttempts(detail.attempts);

  return (
    <div className="space-y-6">
      {errorMessage && detail ? (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Action failed</AlertTitle>
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      ) : null}

      {actionMessage ? (
        <Alert>
          <ClipboardCheck className="h-4 w-4" />
          <AlertTitle>Exam updated</AlertTitle>
          <AlertDescription>{actionMessage}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={getExamStatusBadgeVariant(exam.status)}>{exam.status}</Badge>
                <Badge variant="outline">{getExamModeLabel(exam.exam_mode)}</Badge>
                {openNow ? <Badge variant="default">Open now</Badge> : <Badge variant="outline">Not open</Badge>}
              </div>
              <div>
                <CardTitle className="text-3xl">{exam.title}</CardTitle>
                <CardDescription className="mt-2 text-base">{exam.subject}</CardDescription>
              </div>
              {exam.description ? <p className="max-w-3xl text-sm text-muted-foreground">{exam.description}</p> : null}
            </div>

            {isStudentViewer ? (
              <div className="flex flex-col gap-3">
                <Button onClick={handleStartAttempt} disabled={!canStartAttempt || isStartingAttempt}>
                  {isStartingAttempt ? (
                    <LoaderIcon className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <PlayCircle className="mr-2 h-4 w-4" />
                  )}
                  {currentAttempt ? 'Resume private attempt' : 'Start private attempt'}
                </Button>
                {!detail.enrollment ? (
                  <p className="max-w-xs text-sm text-muted-foreground">
                    You need to join this exam with the teacher code first.
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Card>
            <CardHeader className="pb-3">
              <CardDescription>Duration</CardDescription>
              <CardTitle className="text-2xl">{formatDurationMinutes(exam.duration_minutes)}</CardTitle>
            </CardHeader>
            <CardContent className="pt-0 text-sm text-muted-foreground">
              {exam.question_count} planned prompts
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardDescription>Schedule</CardDescription>
              <CardTitle className="text-lg">
                <ScheduleText startAt={exam.start_at} endAt={exam.end_at} />
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0 text-sm text-muted-foreground">
              {exam.published_at ? `Published ${formatDateTime(exam.published_at)}` : 'Not published yet'}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardDescription>{isTeacherOwner ? 'Join Code' : 'Attempt Policy'}</CardDescription>
              <CardTitle className="text-2xl">
                {isTeacherOwner ? exam.join_code : `${exam.max_attempts_per_student} max`}
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0 text-sm text-muted-foreground">
              {isTeacherOwner ? 'Share this code with students.' : `${completedAttempts} completed so far`}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardDescription>{isTeacherOwner ? 'Exam Activity' : 'Result Visibility'}</CardDescription>
              <CardTitle className="text-2xl">
                {isTeacherOwner
                  ? (detail.stats?.attemptCount ?? 0)
                  : exam.show_results_immediately
                    ? 'Immediate'
                    : 'Hidden'}
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0 text-sm text-muted-foreground">
              {isTeacherOwner
                ? `${detail.stats?.enrollmentCount ?? 0} student enrollments`
                : exam.show_results_immediately
                  ? 'Students can see results as soon as they are evaluated.'
                  : 'Students only see submission status for now.'}
            </CardContent>
          </Card>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Instructions</CardTitle>
              <CardDescription>What students should know before starting the exam.</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                {exam.instructions || 'No extra instructions were provided for this exam.'}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Rubric</CardTitle>
              <CardDescription>The teacher-defined scoring criteria for this exam.</CardDescription>
            </CardHeader>
            <CardContent>
              <RubricCriteriaList criteria={detail.criteria} />
            </CardContent>
          </Card>

          {isTeacherOwner && attemptsResponse ? <TeacherAttemptsTable attemptsResponse={attemptsResponse} /> : null}

          {isStudentViewer ? (
            <Card>
              <CardHeader>
                <CardTitle>My Attempts</CardTitle>
                <CardDescription>
                  Only your own attempts are visible here. Other students never see this list.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <StudentAttemptCards attempts={detail.attempts} hideResults={shouldHideStudentResults} />
              </CardContent>
            </Card>
          ) : null}
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>{isTeacherOwner ? 'Teacher Notes' : 'Student Access'}</CardTitle>
              <CardDescription>
                {isTeacherOwner ? 'How this shared exam behaves.' : 'How your private attempt is isolated.'}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              {isTeacherOwner ? (
                <>
                  <p>One exam can collect many student attempts while keeping each transcript and result private.</p>
                  <p>Open any attempt to review the submission and add rubric-based evaluation scores.</p>
                  <p>
                    Oral mode is already modeled here; the next backend phase will reconnect the realtime examiner to
                    these attempt records.
                  </p>
                </>
              ) : (
                <>
                  <p>
                    Your teacher created one shared exam, but your attempt stays private and separate from every other
                    student.
                  </p>
                  <p>
                    Starting the exam creates or resumes your own attempt record. Nobody else can see your answers or
                    feedback.
                  </p>
                  <p>
                    Oral exams now launch into the Veridex live room. Written exams now run as one-question-at-a-time
                    submissions in the attempt page, while hybrid attempts still use manual completion and review.
                  </p>
                </>
              )}
            </CardContent>
          </Card>

          {isStudentViewer && shouldHideStudentResults ? (
            <Alert>
              <ShieldCheck className="h-4 w-4" />
              <AlertTitle>Results hidden by teacher setting</AlertTitle>
              <AlertDescription>
                Evaluated scores and feedback are intentionally hidden until the later release flow is implemented.
              </AlertDescription>
            </Alert>
          ) : null}

          <Card>
            <CardHeader>
              <CardTitle>Back to Workspace</CardTitle>
              <CardDescription>Return to the shared dashboard listing for all your exams.</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline">
                <Link href="/dashboard/exams">
                  <BookOpen className="mr-2 h-4 w-4" />
                  Open exam workspace
                </Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
