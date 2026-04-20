'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  FileText,
  LoaderIcon,
  Mic,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { EvaluationContestationQueue } from './evaluation-contestation-queue';
import { EvaluationProgressCard } from './evaluation-progress-card';
import { EvaluationResultsPanel } from './evaluation-results-panel';
import { VoiceVerificationPanel, type VoiceVerificationData } from './voice-verification-panel';
import { WrittenExamQuestionFlow } from './written-exam-question-flow';
import { useRealtimeAttemptEvaluation } from '../hooks/use-realtime-attempt-evaluation';
import { fetchExamContext, finishExamAttempt, queueAttemptEvaluation } from '../lib/client';
import {
  formatDateTime,
  formatDurationMinutes,
  formatDurationSeconds,
  getAttemptStatusBadgeVariant,
  getExamModeLabel,
  getScoreBadgeVariant,
} from '../lib/formatters';
import type {
  ExamAttemptResponse,
  ExamCriterionScores,
  ExamRubricCriterion,
  ExamWrittenAnswer,
  UserRole,
} from '../types';

function isTeacherRole(role: UserRole | null) {
  return role === 'teacher' || role === 'admin';
}

function AttemptSkeleton() {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <Skeleton className="h-7 w-72" />
          <Skeleton className="h-4 w-full max-w-xl" />
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
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function buildTranscriptText(attempt: ExamAttemptResponse['attempt']) {
  if (!attempt.conversation_history || attempt.conversation_history.length === 0) {
    return '';
  }

  return attempt.conversation_history
    .map((message) => `${message.role.toUpperCase()}: ${message.content}`)
    .join('\n\n');
}

function buildWrittenAnswerText(attempt: ExamAttemptResponse['attempt']) {
  if (!attempt.written_answers || attempt.written_answers.length === 0) {
    return '';
  }

  return attempt.written_answers
    .map((answer) => answer.student_answer || answer.answer || '')
    .filter(Boolean)
    .join('\n\n');
}

function buildCriterionScoreInputs(criteria: ExamRubricCriterion[], scores: ExamCriterionScores) {
  const values: Record<string, string> = {};

  for (const criterion of criteria) {
    const currentScore = scores?.[criterion.criterion_key]?.score;
    values[criterion.criterion_key] = typeof currentScore === 'number' ? String(currentScore) : '';
  }

  return values;
}

function EvaluationSummary({ title, items }: { title: string; items: string[] | undefined }) {
  if (!items || items.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2">
      <p className="font-medium">{title}</p>
      <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
        {items.map((item, index) => (
          <li key={`${title}-${index}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function CriterionScoreGrid({ criteria, scores }: { criteria: ExamRubricCriterion[]; scores: ExamCriterionScores }) {
  if (criteria.length === 0) {
    return null;
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {criteria.map((criterion) => {
        const currentScore = scores?.[criterion.criterion_key]?.score;
        const currentFeedback = scores?.[criterion.criterion_key]?.feedback;

        return (
          <Card key={criterion.id}>
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <CardTitle className="text-base">{criterion.criterion_label}</CardTitle>
                  <CardDescription>{criterion.weight}% weight</CardDescription>
                </div>
                <Badge variant={getScoreBadgeVariant(typeof currentScore === 'number' ? currentScore : null)}>
                  {typeof currentScore === 'number' ? `${currentScore}/${criterion.score_max}` : 'Pending'}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="pt-0 text-sm text-muted-foreground">
              <p>
                Range: {criterion.score_min} - {criterion.score_max}
              </p>
              {currentFeedback ? <p className="mt-3 whitespace-pre-wrap">{currentFeedback}</p> : null}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

export function ExamAttemptDetail({ attemptId }: { attemptId: string }) {
  const [context, setContext] = useState<Awaited<ReturnType<typeof fetchExamContext>> | null>(null);
  const [isContextLoading, setIsContextLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [actionErrorMessage, setActionErrorMessage] = useState<string | null>(null);
  const [contextErrorMessage, setContextErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [overallScore, setOverallScore] = useState('');
  const [feedback, setFeedback] = useState('');
  const [criterionScoreInputs, setCriterionScoreInputs] = useState<Record<string, string>>({});
  const [transcriptDraft, setTranscriptDraft] = useState('');
  const [writtenDraft, setWrittenDraft] = useState('');
  const {
    attemptResponse,
    isLoading: isAttemptLoading,
    isRefreshing,
    errorMessage: attemptErrorMessage,
    reload,
  } = useRealtimeAttemptEvaluation(attemptId);

  useEffect(() => {
    const initialize = async () => {
      try {
        setContextErrorMessage(null);
        const nextContext = await fetchExamContext();
        setContext(nextContext);
      } catch (error) {
        setContextErrorMessage(error instanceof Error ? error.message : 'Unable to load this attempt context.');
      } finally {
        setIsContextLoading(false);
      }
    };

    void initialize();
  }, [attemptId]);

  useEffect(() => {
    if (!attemptResponse) {
      return;
    }

    setOverallScore(attemptResponse.attempt.overall_score != null ? String(attemptResponse.attempt.overall_score) : '');
    setFeedback(attemptResponse.attempt.feedback || '');
    setCriterionScoreInputs(
      buildCriterionScoreInputs(attemptResponse.criteria, attemptResponse.attempt.criterion_scores),
    );
    setTranscriptDraft(buildTranscriptText(attemptResponse.attempt));
    setWrittenDraft(buildWrittenAnswerText(attemptResponse.attempt));
  }, [attemptResponse]);

  const buildSubmittedAttemptMessage = async (examId: string, nextAttemptId: string) => {
    try {
      await queueAttemptEvaluation(nextAttemptId, { examId });
      return 'Attempt submitted and evaluation started.';
    } catch (error) {
      const reason =
        error instanceof Error ? error.message : 'Unable to trigger evaluator from the frontend after submission.';
      return `Attempt submitted successfully, but evaluation was not queued automatically. ${reason}`;
    }
  };

  const handleTeacherEvaluation = async () => {
    if (!attemptResponse) {
      return;
    }

    const exam = attemptResponse.exam;
    const nextCriterionScores: ExamCriterionScores = {
      ...attemptResponse.attempt.criterion_scores,
    };

    for (const criterion of attemptResponse.criteria) {
      const rawValue = criterionScoreInputs[criterion.criterion_key]?.trim();

      if (!rawValue) {
        continue;
      }

      const parsedValue = Number(rawValue);
      if (!Number.isFinite(parsedValue) || parsedValue < criterion.score_min || parsedValue > criterion.score_max) {
        setActionErrorMessage(
          `${criterion.criterion_label} must be between ${criterion.score_min} and ${criterion.score_max}.`,
        );
        return;
      }

      nextCriterionScores[criterion.criterion_key] = {
        ...nextCriterionScores[criterion.criterion_key],
        score: parsedValue,
      };
    }

    const parsedOverallScore = overallScore.trim().length > 0 ? Number(overallScore) : null;
    if (
      parsedOverallScore != null &&
      (!Number.isFinite(parsedOverallScore) || parsedOverallScore < 0 || parsedOverallScore > 100)
    ) {
      setActionErrorMessage('Overall score must be between 0 and 100.');
      return;
    }

    setIsSaving(true);
    setActionErrorMessage(null);
    setSuccessMessage(null);

    try {
      const response = await finishExamAttempt(exam.id, attemptResponse.attempt.id, {
        status: 'evaluated',
        overallScore: parsedOverallScore,
        feedback: feedback.trim() || null,
        criterionScores: nextCriterionScores,
      });

      setSuccessMessage(response.message || 'Evaluation saved successfully.');
      await reload();
    } catch (error) {
      setActionErrorMessage(error instanceof Error ? error.message : 'Unable to save the evaluation.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleStudentAttemptUpdate = async (status: 'submitted' | 'cancelled') => {
    if (!attemptResponse) {
      return;
    }

    const exam = attemptResponse.exam;
    const shouldIncludeTranscript = exam.exam_mode === 'oral' || exam.exam_mode === 'hybrid';
    const shouldIncludeWritten = exam.exam_mode === 'hybrid';
    const trimmedTranscript = transcriptDraft.trim();
    const trimmedWritten = writtenDraft.trim();

    if (status === 'submitted') {
      if (shouldIncludeTranscript && trimmedTranscript.length === 0 && !shouldIncludeWritten) {
        setActionErrorMessage('Add a transcript or answer summary before submitting this oral attempt.');
        return;
      }

      if (shouldIncludeWritten && trimmedWritten.length === 0 && !shouldIncludeTranscript) {
        setActionErrorMessage('Add a written answer before submitting this attempt.');
        return;
      }

      if (exam.exam_mode === 'hybrid' && trimmedTranscript.length === 0 && trimmedWritten.length === 0) {
        setActionErrorMessage('Add a transcript, a written answer, or both before submitting.');
        return;
      }
    }

    setIsSaving(true);
    setActionErrorMessage(null);
    setSuccessMessage(null);

    try {
      const response = await finishExamAttempt(exam.id, attemptResponse.attempt.id, {
        status,
        conversationHistory:
          status === 'submitted' && shouldIncludeTranscript && trimmedTranscript.length > 0
            ? [{ role: 'user', content: trimmedTranscript, timestamp: new Date().toISOString() }]
            : undefined,
        writtenAnswers:
          status === 'submitted' && shouldIncludeWritten && trimmedWritten.length > 0
            ? [
                {
                  question_id: 'phase3-manual-submission',
                  question_text: exam.instructions || 'Veridex manual submission',
                  student_answer: trimmedWritten,
                  answer: trimmedWritten,
                },
              ]
            : undefined,
      });

      let successMessage =
        response.message ||
        (status === 'submitted' ? 'Attempt submitted successfully.' : 'Attempt cancelled successfully.');

      if (status === 'submitted' && response.attempt.status === 'submitted') {
        successMessage = await buildSubmittedAttemptMessage(exam.id, response.attempt.id);
      }

      setSuccessMessage(successMessage);
      await reload();
    } catch (error) {
      setActionErrorMessage(error instanceof Error ? error.message : 'Unable to update the attempt.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleWrittenAttemptSubmit = async (writtenAnswers: ExamWrittenAnswer[]) => {
    if (!attemptResponse) {
      return;
    }

    const exam = attemptResponse.exam;

    setIsSaving(true);
    setActionErrorMessage(null);
    setSuccessMessage(null);

    try {
      const response = await finishExamAttempt(exam.id, attemptResponse.attempt.id, {
        status: 'submitted',
        writtenAnswers,
      });

      let successMessage = response.message || 'Attempt submitted successfully.';
      if (response.attempt.status === 'submitted') {
        successMessage = await buildSubmittedAttemptMessage(exam.id, response.attempt.id);
      }

      setSuccessMessage(successMessage);
      await reload();
    } catch (error) {
      setActionErrorMessage(error instanceof Error ? error.message : 'Unable to submit the written attempt.');
    } finally {
      setIsSaving(false);
    }
  };

  const isLoading = isContextLoading || isAttemptLoading;
  const pageErrorMessage = contextErrorMessage || attemptErrorMessage;

  if (isLoading) {
    return <AttemptSkeleton />;
  }

  if (pageErrorMessage && !attemptResponse) {
    return (
      <Card>
        <CardContent className="py-10">
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Attempt not available</AlertTitle>
            <AlertDescription>{pageErrorMessage}</AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  if (!attemptResponse || !context?.role) {
    return (
      <Card>
        <CardContent className="py-10">
          <Alert>
            <ShieldCheck className="h-4 w-4" />
            <AlertTitle>Profile required</AlertTitle>
            <AlertDescription>Complete the new exam profile flow before opening attempt details.</AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  const exam = attemptResponse.exam;
  const attempt = attemptResponse.attempt;
  const questions = attemptResponse.questions ?? [];
  const questionResults = attemptResponse.questionResults ?? [];
  const reEvalRequests = attemptResponse.reEvalRequests ?? [];
  const hasQuestionResults = questionResults.length > 0;
  const isTeacherOwner = isTeacherRole(context.role) && context.context.user_id === exam.teacher_user_id;
  const isStudentOwner = context.context.user_id === attempt.student_user_id;
  const isStudentAnsweringWrittenAttempt =
    isStudentOwner && attempt.status === 'in_progress' && exam.exam_mode === 'written';
  const hideStudentResults = isStudentOwner && !isTeacherOwner && !exam.show_results_immediately;
  const canShowEvaluation = (!hideStudentResults || isTeacherOwner) && !isStudentAnsweringWrittenAttempt;
  const evaluatorSummary = attempt.evaluator_summary || {};
  const showTranscript = exam.exam_mode === 'oral' || exam.exam_mode === 'hybrid';
  const showWrittenAnswers = exam.exam_mode === 'written' || exam.exam_mode === 'hybrid';
  const supportsLiveOralRoom = exam.exam_mode === 'oral';
  const scoreSummaryPercentage =
    typeof attemptResponse.scoreSummary?.percentage === 'number' ? attemptResponse.scoreSummary.percentage : null;
  const displayedOverallScore =
    typeof attempt.overall_score === 'number' ? attempt.overall_score : scoreSummaryPercentage;

  return (
    <div className="space-y-6">
      {actionErrorMessage ? (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Action failed</AlertTitle>
          <AlertDescription>{actionErrorMessage}</AlertDescription>
        </Alert>
      ) : null}

      {successMessage ? (
        <Alert>
          <CheckCircle2 className="h-4 w-4" />
          <AlertTitle>Attempt updated</AlertTitle>
          <AlertDescription>{successMessage}</AlertDescription>
        </Alert>
      ) : null}

      {pageErrorMessage && attemptResponse ? (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Live sync issue</AlertTitle>
          <AlertDescription>{pageErrorMessage}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline">{getExamModeLabel(exam.exam_mode)}</Badge>
                <Badge variant={getAttemptStatusBadgeVariant(attempt.status)}>{attempt.status}</Badge>
                {displayedOverallScore != null && canShowEvaluation ? (
                  <Badge variant={getScoreBadgeVariant(displayedOverallScore)}>{displayedOverallScore}/100</Badge>
                ) : null}
                {isRefreshing ? (
                  <Badge variant="secondary">
                    <LoaderIcon className="mr-1 h-3.5 w-3.5 animate-spin" />
                    Syncing
                  </Badge>
                ) : null}
              </div>

              <div>
                <CardTitle className="text-3xl">{exam.title}</CardTitle>
                <CardDescription className="mt-2 text-base">
                  Attempt {attempt.attempt_number} for {exam.subject}
                </CardDescription>
              </div>
            </div>

            <Button asChild variant="outline">
              <Link href={`/dashboard/exams/${exam.id}`}>
                Back to exam
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Card>
            <CardHeader className="pb-3">
              <CardDescription>Started</CardDescription>
              <CardTitle className="text-lg">{formatDateTime(attempt.started_at)}</CardTitle>
            </CardHeader>
            <CardContent className="pt-0 text-sm text-muted-foreground">
              {attempt.ended_at ? `Ended ${formatDateTime(attempt.ended_at)}` : 'Still in progress'}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardDescription>Duration</CardDescription>
              <CardTitle className="text-2xl">{formatDurationSeconds(attempt.duration_seconds)}</CardTitle>
            </CardHeader>
            <CardContent className="pt-0 text-sm text-muted-foreground">
              {formatDurationMinutes(exam.duration_minutes)} target
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardDescription>Content Stored</CardDescription>
              <CardTitle className="text-2xl">
                {attempt.conversation_history.length + attempt.written_answers.length}
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0 text-sm text-muted-foreground">
              {showTranscript ? 'Transcript enabled.' : 'No transcript'}{' '}
              {showWrittenAnswers ? 'Written answers enabled.' : ''}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardDescription>Result Visibility</CardDescription>
              <CardTitle className="text-2xl">
                {isTeacherOwner ? 'Teacher' : exam.show_results_immediately ? 'Visible' : 'Hidden'}
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0 text-sm text-muted-foreground">
              {isTeacherOwner
                ? 'You can always review and evaluate this attempt.'
                : exam.show_results_immediately
                  ? 'Results will appear after evaluation.'
                  : 'Students only see submission status for now.'}
            </CardContent>
          </Card>
        </CardContent>
      </Card>

      {!isStudentAnsweringWrittenAttempt && hideStudentResults ? (
        <Alert>
          <ShieldCheck className="h-4 w-4" />
          <AlertTitle>Evaluation hidden by teacher setting</AlertTitle>
          <AlertDescription>
            This attempt may already be scored, but detailed results stay hidden until later release flows are added.
          </AlertDescription>
        </Alert>
      ) : null}

      {!isStudentAnsweringWrittenAttempt && canShowEvaluation ? (
        <EvaluationProgressCard attempt={attempt} scoreSummaryPercentage={scoreSummaryPercentage} />
      ) : null}

      {isStudentOwner && attempt.status === 'in_progress' && supportsLiveOralRoom ? (
        <Card>
          <CardHeader>
            <CardTitle>Veridex Oral Room</CardTitle>
            <CardDescription>
              This attempt is connected to the live oral examiner. Launch the room to speak with the AI examiner and
              store the transcript directly on this attempt.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <p className="text-sm text-muted-foreground">
              Your transcript and final evaluation remain private to this attempt and the teacher who owns the exam.
            </p>
            <Button asChild>
              <Link href={`/dashboard/exams/attempts/${attempt.id}/oral`}>
                Launch Oral Room
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {isStudentOwner && attempt.status === 'in_progress' && exam.exam_mode === 'written' ? (
        <WrittenExamQuestionFlow
          questions={questions}
          initialAnswers={attempt.written_answers}
          isSubmitting={isSaving}
          onSubmit={handleWrittenAttemptSubmit}
          onCancelAttempt={() => handleStudentAttemptUpdate('cancelled')}
        />
      ) : null}

      {isStudentOwner && attempt.status === 'in_progress' && exam.exam_mode === 'hybrid' ? (
        <Card>
          <CardHeader>
            <CardTitle>Manual Submission Workspace</CardTitle>
            <CardDescription>
              This page lets you store a manual transcript or written response for hybrid attempts that are not yet
              handled entirely inside the live oral room.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {showTranscript ? (
              <div className="space-y-2">
                <Label htmlFor="transcript-draft">Transcript or Oral Answer Summary</Label>
                <textarea
                  id="transcript-draft"
                  value={transcriptDraft}
                  onChange={(event) => setTranscriptDraft(event.target.value)}
                  placeholder="Paste or type the student's oral response summary here..."
                  className="flex min-h-[180px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                />
              </div>
            ) : null}

            {showWrittenAnswers ? (
              <div className="space-y-2">
                <Label htmlFor="written-draft">Written Answer</Label>
                <textarea
                  id="written-draft"
                  value={writtenDraft}
                  onChange={(event) => setWrittenDraft(event.target.value)}
                  placeholder="Write or paste the student's written answer here..."
                  className="flex min-h-[180px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                />
              </div>
            ) : null}

            <div className="flex flex-col gap-3 md:flex-row">
              <Button onClick={() => handleStudentAttemptUpdate('submitted')} disabled={isSaving}>
                {isSaving ? (
                  <LoaderIcon className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <ClipboardCheck className="mr-2 h-4 w-4" />
                )}
                Submit attempt
              </Button>
              <Button variant="outline" onClick={() => handleStudentAttemptUpdate('cancelled')} disabled={isSaving}>
                Cancel attempt
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {!isStudentAnsweringWrittenAttempt ? (
        <div className="grid gap-6 xl:grid-cols-3">
          <div className="space-y-6 xl:col-span-2">
            {showTranscript ? (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Mic className="h-4 w-4" />
                    Transcript
                  </CardTitle>
                  <CardDescription>Stored conversation history for this attempt.</CardDescription>
                </CardHeader>
                <CardContent>
                  {attempt.conversation_history.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No transcript has been stored for this attempt yet.</p>
                  ) : (
                    <div className="space-y-3">
                      {attempt.conversation_history.map((message, index) => (
                        <div key={`${message.timestamp}-${index}`} className="rounded-lg border border-border p-4">
                          <div className="mb-2 flex items-center gap-2">
                            <Badge variant="outline">{message.role}</Badge>
                            <span className="text-xs text-muted-foreground">{formatDateTime(message.timestamp)}</span>
                          </div>
                          <p className="whitespace-pre-wrap text-sm text-muted-foreground">{message.content}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            ) : null}

            {showWrittenAnswers ? (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <FileText className="h-4 w-4" />
                    Written Answers
                  </CardTitle>
                  <CardDescription>Stored written responses for this attempt.</CardDescription>
                </CardHeader>
                <CardContent>
                  {attempt.written_answers.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No written answers have been stored for this attempt yet.
                    </p>
                  ) : (
                    <div className="space-y-4">
                      {attempt.written_answers.map((answer, index) => (
                        <div
                          key={`${answer.question_id || 'answer'}-${index}`}
                          className="rounded-lg border border-border p-4"
                        >
                          <p className="text-sm font-medium">{answer.question_text || `Answer ${index + 1}`}</p>
                          <p className="mt-3 whitespace-pre-wrap text-sm text-muted-foreground">
                            {answer.student_answer || answer.answer || 'No answer stored.'}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            ) : null}

            {canShowEvaluation ? (
              <Card>
                <CardHeader>
                  <CardTitle>Rubric Scores</CardTitle>
                  <CardDescription>Criterion-level scoring saved against this attempt.</CardDescription>
                </CardHeader>
                <CardContent>
                  <CriterionScoreGrid criteria={attemptResponse.criteria} scores={attempt.criterion_scores} />
                </CardContent>
              </Card>
            ) : null}

            <EvaluationResultsPanel
              attemptId={attempt.id}
              questions={questions}
              questionResults={questionResults}
              reEvalRequests={reEvalRequests}
              isStudentOwner={isStudentOwner}
              isTeacherOwner={isTeacherOwner}
              canShowEvaluation={canShowEvaluation}
              onChanged={reload}
            />

            {(isTeacherOwner || isStudentOwner) && exam.exam_mode !== 'written' ? (
              <VoiceVerificationPanel
                verification={(attempt.voice_verification as VoiceVerificationData | null | undefined) ?? null}
              />
            ) : null}

            {canShowEvaluation ? (
              <Card>
                <CardHeader>
                  <CardTitle>Feedback</CardTitle>
                  <CardDescription>Teacher or evaluator comments stored on the attempt.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                    {attempt.feedback || 'No feedback has been stored yet.'}
                  </p>

                  <div className="grid gap-6 md:grid-cols-3">
                    <EvaluationSummary title="Strengths" items={evaluatorSummary.strengths} />
                    <EvaluationSummary title="Improvements" items={evaluatorSummary.improvements} />
                    <EvaluationSummary title="Recommendations" items={evaluatorSummary.recommendations} />
                  </div>
                </CardContent>
              </Card>
            ) : null}
          </div>

          <div className="space-y-6">
            {isTeacherOwner ? (
              hasQuestionResults ? (
                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <CardTitle>Teacher Controls</CardTitle>
                        <CardDescription>
                          Veridex is now writing question-level results for this attempt. Manual edits belong in the
                          question results panel so totals recalculate immediately.
                        </CardDescription>
                      </div>
                      <Badge variant="outline">
                        <Sparkles className="mr-1 h-3.5 w-3.5" />
                        Teacher
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3 text-sm text-muted-foreground">
                    <p>
                      Use the &quot;Adjust score&quot; action on any evaluated question to override the score and keep
                      the attempt total in sync.
                    </p>
                    <p>
                      Student reclamations for this attempt will appear in the queue below as soon as they are
                      submitted.
                    </p>
                  </CardContent>
                </Card>
              ) : (
                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <CardTitle>Teacher Evaluation</CardTitle>
                        <CardDescription>
                          Score this attempt with the exam rubric and publish feedback to the record.
                        </CardDescription>
                      </div>
                      <Badge variant="outline">
                        <Sparkles className="mr-1 h-3.5 w-3.5" />
                        Teacher
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-5">
                    <div className="space-y-2">
                      <Label htmlFor="overall-score">Overall Score</Label>
                      <Input
                        id="overall-score"
                        type="number"
                        min={0}
                        max={100}
                        value={overallScore}
                        onChange={(event) => setOverallScore(event.target.value)}
                        placeholder="0 - 100"
                      />
                    </div>

                    <div className="space-y-3">
                      <p className="text-sm font-medium">Criterion Scores</p>
                      {attemptResponse.criteria.map((criterion) => (
                        <div key={criterion.id} className="space-y-2">
                          <Label htmlFor={`criterion-${criterion.criterion_key}`}>
                            {criterion.criterion_label} ({criterion.score_min} - {criterion.score_max})
                          </Label>
                          <Input
                            id={`criterion-${criterion.criterion_key}`}
                            type="number"
                            min={criterion.score_min}
                            max={criterion.score_max}
                            value={criterionScoreInputs[criterion.criterion_key] || ''}
                            onChange={(event) =>
                              setCriterionScoreInputs((currentValues) => ({
                                ...currentValues,
                                [criterion.criterion_key]: event.target.value,
                              }))
                            }
                            placeholder={`${criterion.score_min} - ${criterion.score_max}`}
                          />
                        </div>
                      ))}
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="teacher-feedback">Feedback</Label>
                      <textarea
                        id="teacher-feedback"
                        value={feedback}
                        onChange={(event) => setFeedback(event.target.value)}
                        placeholder="Summarize strengths, weaknesses, and next steps."
                        className="flex min-h-[180px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                      />
                    </div>

                    <Button onClick={handleTeacherEvaluation} disabled={isSaving}>
                      {isSaving ? (
                        <LoaderIcon className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <ClipboardCheck className="mr-2 h-4 w-4" />
                      )}
                      Save evaluation
                    </Button>
                  </CardContent>
                </Card>
              )
            ) : (
              <Card>
                <CardHeader>
                  <CardTitle>Attempt Privacy</CardTitle>
                  <CardDescription>This record belongs only to you and your teacher.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-sm text-muted-foreground">
                  <p>
                    Other students cannot see this attempt, your transcript, your written answers, or your evaluation.
                  </p>
                  <p>
                    This page is the private attempt record that sits underneath the shared teacher exam and keeps each
                    student submission isolated.
                  </p>
                </CardContent>
              </Card>
            )}

            <EvaluationContestationQueue
              reEvalRequests={reEvalRequests}
              questions={questions}
              isTeacherOwner={isTeacherOwner}
              onChanged={reload}
            />

            <Card>
              <CardHeader>
                <CardTitle>Exam Context</CardTitle>
                <CardDescription>Reference information pulled from the shared exam template.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-muted-foreground">
                <p>Mode: {getExamModeLabel(exam.exam_mode)}</p>
                <p>Duration: {formatDurationMinutes(exam.duration_minutes)}</p>
                <p>Questions: {exam.question_count}</p>
                <p>Instructions: {exam.instructions || 'No instructions provided.'}</p>
              </CardContent>
            </Card>

            <Button asChild variant="outline">
              <Link href="/dashboard/exams">
                Open exam workspace
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
