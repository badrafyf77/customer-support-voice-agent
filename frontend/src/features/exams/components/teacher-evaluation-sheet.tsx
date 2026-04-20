'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  ExternalLink,
  FileText,
  LoaderIcon,
  Mic,
  PencilLine,
  Sparkles,
  User,
} from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { EvaluationContestationQueue } from './evaluation-contestation-queue';
import { EvaluationResultsPanel } from './evaluation-results-panel';
import { useRealtimeAttemptEvaluation } from '../hooks/use-realtime-attempt-evaluation';
import { finishExamAttempt } from '../lib/client';
import {
  formatDateTime,
  formatDurationSeconds,
  getAttemptStatusBadgeVariant,
  getExamModeLabel,
  getScoreBadgeVariant,
} from '../lib/formatters';
import type { EvaluationScoreSummary, ExamCriterionScores, ExamRubricCriterion } from '../types';

function buildCriterionInputs(criteria: ExamRubricCriterion[], scores: ExamCriterionScores) {
  const values: Record<string, string> = {};
  for (const criterion of criteria) {
    const s = scores?.[criterion.criterion_key]?.score;
    values[criterion.criterion_key] = typeof s === 'number' ? String(s) : '';
  }
  return values;
}

interface TeacherEvaluationSheetProps {
  attemptId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function TeacherEvaluationSheet({ attemptId, open, onOpenChange }: TeacherEvaluationSheetProps) {
  const { attemptResponse, isLoading, isRefreshing, errorMessage, reload } = useRealtimeAttemptEvaluation(
    attemptId ?? '',
  );

  const [isSaving, setIsSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [overallScore, setOverallScore] = useState('');
  const [feedback, setFeedback] = useState('');
  const [criterionInputs, setCriterionInputs] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!attemptResponse) return;
    setOverallScore(attemptResponse.attempt.overall_score != null ? String(attemptResponse.attempt.overall_score) : '');
    setFeedback(attemptResponse.attempt.feedback || '');
    setCriterionInputs(buildCriterionInputs(attemptResponse.criteria, attemptResponse.attempt.criterion_scores));
  }, [attemptResponse]);

  // Reset messages when a new attempt is loaded
  useEffect(() => {
    setActionError(null);
    setSuccessMessage(null);
  }, [attemptId]);

  const handleSaveEvaluation = async () => {
    if (!attemptResponse) return;

    const nextCriterionScores: ExamCriterionScores = { ...attemptResponse.attempt.criterion_scores };

    for (const criterion of attemptResponse.criteria) {
      const raw = criterionInputs[criterion.criterion_key]?.trim();
      if (!raw) continue;
      const parsed = Number(raw);
      if (!Number.isFinite(parsed) || parsed < criterion.score_min || parsed > criterion.score_max) {
        setActionError(`${criterion.criterion_label} must be between ${criterion.score_min} and ${criterion.score_max}.`);
        return;
      }
      nextCriterionScores[criterion.criterion_key] = { ...nextCriterionScores[criterion.criterion_key], score: parsed };
    }

    const parsedOverall = overallScore.trim() ? Number(overallScore) : null;
    if (parsedOverall != null && (!Number.isFinite(parsedOverall) || parsedOverall < 0 || parsedOverall > 100)) {
      setActionError('Overall score must be between 0 and 100.');
      return;
    }

    setIsSaving(true);
    setActionError(null);
    setSuccessMessage(null);

    try {
      const res = await finishExamAttempt(attemptResponse.exam.id, attemptResponse.attempt.id, {
        status: 'evaluated',
        overallScore: parsedOverall,
        feedback: feedback.trim() || null,
        criterionScores: nextCriterionScores,
      });
      setSuccessMessage(res.message || 'Evaluation saved successfully.');
      await reload();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Unable to save the evaluation.');
    } finally {
      setIsSaving(false);
    }
  };

  if (!attemptId || !open) return null;

  const exam = attemptResponse?.exam;
  const attempt = attemptResponse?.attempt;
  const criteria = attemptResponse?.criteria ?? [];
  const questions = attemptResponse?.questions ?? [];
  const questionResults = attemptResponse?.questionResults ?? [];
  const reEvalRequests = attemptResponse?.reEvalRequests ?? [];
  const hasQuestionResults = questionResults.length > 0;
  const scoreSummary: EvaluationScoreSummary | undefined = attemptResponse?.scoreSummary;
  const evaluatorSummary = (attempt?.evaluator_summary as Record<string, unknown> | null) ?? {};
  const displayedOverallScore =
    typeof attempt?.overall_score === 'number'
      ? attempt.overall_score
      : typeof scoreSummary?.percentage === 'number'
        ? scoreSummary.percentage
        : null;
  const showTranscript = exam?.exam_mode === 'oral' || exam?.exam_mode === 'hybrid';
  const showWrittenAnswers = exam?.exam_mode === 'written' || exam?.exam_mode === 'hybrid';

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-0 overflow-hidden p-0 sm:max-w-3xl"
      >
        {/* Header */}
        <SheetHeader className="border-b px-6 py-4">
          <div className="flex items-start justify-between gap-4 pr-6">
            <div className="space-y-1">
              <SheetTitle className="text-xl">
                {exam ? exam.title : 'Loading evaluation…'}
              </SheetTitle>
              <SheetDescription>
                {exam && attempt ? (
                  <span className="flex flex-wrap items-center gap-2">
                    <Badge variant={getAttemptStatusBadgeVariant(attempt.status)}>{attempt.status}</Badge>
                    <Badge variant="outline">{getExamModeLabel(exam.exam_mode)}</Badge>
                    {displayedOverallScore != null && (
                      <Badge variant={getScoreBadgeVariant(displayedOverallScore)}>{displayedOverallScore}/100</Badge>
                    )}
                    {isRefreshing && (
                      <Badge variant="secondary">
                        <LoaderIcon className="mr-1 h-3 w-3 animate-spin" />
                        Syncing
                      </Badge>
                    )}
                  </span>
                ) : (
                  'Teacher evaluation detail'
                )}
              </SheetDescription>
            </div>

            {attempt && (
              <Button asChild variant="ghost" size="sm" className="shrink-0">
                <Link href={`/dashboard/exams/attempts/${attempt.id}`} target="_blank">
                  <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
                  Full page
                </Link>
              </Button>
            )}
          </div>
        </SheetHeader>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center py-20">
              <LoaderIcon className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : errorMessage && !attemptResponse ? (
            <div className="p-6">
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Unable to load</AlertTitle>
                <AlertDescription>{errorMessage}</AlertDescription>
              </Alert>
            </div>
          ) : attemptResponse && exam && attempt ? (
            <Tabs defaultValue="overview" className="flex h-full flex-col">
              <div className="border-b px-6">
                <TabsList className="h-10">
                  <TabsTrigger value="overview">Overview</TabsTrigger>
                  <TabsTrigger value="questions">
                    Questions
                    {hasQuestionResults && (
                      <Badge variant="secondary" className="ml-1.5 h-4 px-1.5 text-xs">
                        {questionResults.length}
                      </Badge>
                    )}
                  </TabsTrigger>
                  <TabsTrigger value="content">Transcript / Answers</TabsTrigger>
                  <TabsTrigger value="contestations">
                    Reclamations
                    {reEvalRequests.filter((r) => r.status === 'pending').length > 0 && (
                      <Badge variant="destructive" className="ml-1.5 h-4 px-1.5 text-xs">
                        {reEvalRequests.filter((r) => r.status === 'pending').length}
                      </Badge>
                    )}
                  </TabsTrigger>
                </TabsList>
              </div>

              {/* ── Overview tab ── */}
              <TabsContent value="overview" className="mt-0 flex-1 overflow-y-auto">
                <div className="space-y-6 p-6">
                  {actionError && (
                    <Alert variant="destructive">
                      <AlertCircle className="h-4 w-4" />
                      <AlertTitle>Action failed</AlertTitle>
                      <AlertDescription>{actionError}</AlertDescription>
                    </Alert>
                  )}
                  {successMessage && (
                    <Alert>
                      <CheckCircle2 className="h-4 w-4" />
                      <AlertTitle>Saved</AlertTitle>
                      <AlertDescription>{successMessage}</AlertDescription>
                    </Alert>
                  )}

                  {/* Student + attempt meta */}
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="flex items-center gap-2 text-base">
                        <User className="h-4 w-4" />
                        Student &amp; Attempt
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="grid gap-3 text-sm sm:grid-cols-2">
                      <div>
                        <p className="font-medium text-foreground">
                          {attemptResponse.studentProfile?.full_name || 'Unknown student'}
                        </p>
                        <p className="text-muted-foreground">
                          {attemptResponse.studentProfile?.email || attempt.student_user_id}
                        </p>
                      </div>
                      <div className="space-y-1 text-muted-foreground">
                        <p>Attempt {attempt.attempt_number}</p>
                        <p>Started {formatDateTime(attempt.started_at)}</p>
                        {attempt.ended_at && <p>Ended {formatDateTime(attempt.ended_at)}</p>}
                        <p>Duration {formatDurationSeconds(attempt.duration_seconds)}</p>
                      </div>
                    </CardContent>
                  </Card>

                  {/* Score summary */}
                  {scoreSummary != null ? (
                    <Card>
                      <CardHeader className="pb-3">
                        <CardTitle className="text-base">Score Summary</CardTitle>
                      </CardHeader>
                      <CardContent className="grid gap-3 text-sm sm:grid-cols-3">
                        <div className="rounded-lg border p-3 text-center">
                          <p className="text-2xl font-bold">{scoreSummary.total_score}</p>
                          <p className="text-muted-foreground">Total points</p>
                        </div>
                        <div className="rounded-lg border p-3 text-center">
                          <p className="text-2xl font-bold">{scoreSummary.max_total_score}</p>
                          <p className="text-muted-foreground">Max points</p>
                        </div>
                        <div className="rounded-lg border p-3 text-center">
                          <p className="text-2xl font-bold">{scoreSummary.percentage.toFixed(1)}%</p>
                          <p className="text-muted-foreground">Percentage</p>
                        </div>
                      </CardContent>
                    </Card>
                  ) : null}

                  {/* Rubric criteria */}
                  {criteria.length > 0 && (
                    <Card>
                      <CardHeader className="pb-3">
                        <CardTitle className="text-base">Rubric Criteria</CardTitle>
                        <CardDescription>Current AI-assigned scores per criterion.</CardDescription>
                      </CardHeader>
                      <CardContent className="space-y-2">
                        {criteria.map((criterion) => {
                          const s = attempt.criterion_scores?.[criterion.criterion_key]?.score;
                          const fb = attempt.criterion_scores?.[criterion.criterion_key]?.feedback;
                          return (
                            <div key={criterion.id} className="rounded-lg border p-3 text-sm">
                              <div className="flex items-center justify-between gap-3">
                                <div>
                                  <span className="font-medium">{criterion.criterion_label}</span>
                                  <span className="ml-2 text-muted-foreground">({criterion.weight}%)</span>
                                </div>
                                <Badge variant={getScoreBadgeVariant(typeof s === 'number' ? s : null)}>
                                  {typeof s === 'number' ? `${s}/${criterion.score_max}` : 'Pending'}
                                </Badge>
                              </div>
                              {fb && <p className="mt-2 text-muted-foreground">{fb}</p>}
                            </div>
                          );
                        })}
                      </CardContent>
                    </Card>
                  )}

                  {/* AI Feedback */}
                  {(Boolean(attempt.feedback) ||
                    Array.isArray(evaluatorSummary.strengths) ||
                    Array.isArray(evaluatorSummary.improvements) ||
                    Array.isArray(evaluatorSummary.recommendations)) ? (
                    <Card>
                      <CardHeader className="pb-3">
                        <CardTitle className="text-base">AI Evaluator Feedback</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-4 text-sm text-muted-foreground">
                        {attempt.feedback ? <p className="whitespace-pre-wrap">{attempt.feedback}</p> : null}
                        {Array.isArray(evaluatorSummary.strengths) && evaluatorSummary.strengths.length > 0 ? (
                          <div>
                            <p className="font-medium text-foreground">Strengths</p>
                            <ul className="mt-1 list-disc pl-5 space-y-0.5">
                              {(evaluatorSummary.strengths as string[]).map((s, i) => <li key={i}>{s}</li>)}
                            </ul>
                          </div>
                        ) : null}
                        {Array.isArray(evaluatorSummary.improvements) && evaluatorSummary.improvements.length > 0 ? (
                          <div>
                            <p className="font-medium text-foreground">Improvements</p>
                            <ul className="mt-1 list-disc pl-5 space-y-0.5">
                              {(evaluatorSummary.improvements as string[]).map((s, i) => <li key={i}>{s}</li>)}
                            </ul>
                          </div>
                        ) : null}
                        {Array.isArray(evaluatorSummary.recommendations) && evaluatorSummary.recommendations.length > 0 ? (
                          <div>
                            <p className="font-medium text-foreground">Recommendations</p>
                            <ul className="mt-1 list-disc pl-5 space-y-0.5">
                              {(evaluatorSummary.recommendations as string[]).map((s, i) => <li key={i}>{s}</li>)}
                            </ul>
                          </div>
                        ) : null}
                      </CardContent>
                    </Card>
                  ) : null}

                  <Separator />

                  {/* ── Teacher edit form ── */}
                  <div className="space-y-4">
                    <div className="flex items-center gap-2">
                      <PencilLine className="h-4 w-4" />
                      <h3 className="font-semibold">
                        {hasQuestionResults ? 'Override Evaluation' : 'Manual Evaluation'}
                      </h3>
                      <Badge variant="outline">
                        <Sparkles className="mr-1 h-3.5 w-3.5" />
                        Teacher only
                      </Badge>
                    </div>

                    {hasQuestionResults && (
                      <Alert>
                        <Sparkles className="h-4 w-4" />
                        <AlertTitle>AI results available</AlertTitle>
                        <AlertDescription>
                          Use the <strong>Questions</strong> tab to adjust individual question scores. The fields below let you override the overall total and add a teacher note.
                        </AlertDescription>
                      </Alert>
                    )}

                    <div className="space-y-2">
                      <Label htmlFor="sheet-overall-score">Overall Score (0 – 100)</Label>
                      <Input
                        id="sheet-overall-score"
                        type="number"
                        min={0}
                        max={100}
                        value={overallScore}
                        onChange={(e) => setOverallScore(e.target.value)}
                        placeholder="Leave blank to keep AI total"
                      />
                    </div>

                    {!hasQuestionResults && criteria.length > 0 && (
                      <div className="space-y-3">
                        <p className="text-sm font-medium">Criterion Scores</p>
                        {criteria.map((criterion) => (
                          <div key={criterion.id} className="space-y-1.5">
                            <Label htmlFor={`sheet-criterion-${criterion.criterion_key}`}>
                              {criterion.criterion_label} ({criterion.score_min}–{criterion.score_max})
                            </Label>
                            <Input
                              id={`sheet-criterion-${criterion.criterion_key}`}
                              type="number"
                              min={criterion.score_min}
                              max={criterion.score_max}
                              value={criterionInputs[criterion.criterion_key] || ''}
                              onChange={(e) =>
                                setCriterionInputs((prev) => ({ ...prev, [criterion.criterion_key]: e.target.value }))
                              }
                              placeholder={`${criterion.score_min} – ${criterion.score_max}`}
                            />
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="space-y-2">
                      <Label htmlFor="sheet-feedback">Teacher Feedback</Label>
                      <textarea
                        id="sheet-feedback"
                        value={feedback}
                        onChange={(e) => setFeedback(e.target.value)}
                        placeholder="Summarize strengths, weaknesses, and next steps for this student."
                        className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                      />
                    </div>

                    <Button onClick={handleSaveEvaluation} disabled={isSaving}>
                      {isSaving ? (
                        <LoaderIcon className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <ClipboardCheck className="mr-2 h-4 w-4" />
                      )}
                      Save evaluation
                    </Button>
                  </div>
                </div>
              </TabsContent>

              {/* ── Questions tab ── */}
              <TabsContent value="questions" className="mt-0 flex-1 overflow-y-auto">
                <div className="p-6">
                  <EvaluationResultsPanel
                    attemptId={attempt.id}
                    questions={questions}
                    questionResults={questionResults}
                    reEvalRequests={reEvalRequests}
                    isStudentOwner={false}
                    isTeacherOwner={true}
                    canShowEvaluation={true}
                    onChanged={reload}
                  />
                </div>
              </TabsContent>

              {/* ── Content tab ── */}
              <TabsContent value="content" className="mt-0 flex-1 overflow-y-auto">
                <div className="space-y-6 p-6">
                  {showTranscript && (
                    <Card>
                      <CardHeader className="pb-3">
                        <CardTitle className="flex items-center gap-2 text-base">
                          <Mic className="h-4 w-4" />
                          Transcript
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        {attempt.conversation_history.length === 0 ? (
                          <p className="text-sm text-muted-foreground">No transcript stored for this attempt.</p>
                        ) : (
                          <div className="space-y-3">
                            {attempt.conversation_history.map((msg, i) => (
                              <div key={`${msg.timestamp}-${i}`} className="rounded-lg border p-4">
                                <div className="mb-2 flex items-center gap-2">
                                  <Badge variant="outline">{msg.role}</Badge>
                                  <span className="text-xs text-muted-foreground">{formatDateTime(msg.timestamp)}</span>
                                </div>
                                <p className="whitespace-pre-wrap text-sm text-muted-foreground">{msg.content}</p>
                              </div>
                            ))}
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  )}

                  {showWrittenAnswers && (
                    <Card>
                      <CardHeader className="pb-3">
                        <CardTitle className="flex items-center gap-2 text-base">
                          <FileText className="h-4 w-4" />
                          Written Answers
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        {attempt.written_answers.length === 0 ? (
                          <p className="text-sm text-muted-foreground">No written answers stored for this attempt.</p>
                        ) : (
                          <div className="space-y-4">
                            {attempt.written_answers.map((answer, i) => (
                              <div key={`${answer.question_id || 'a'}-${i}`} className="rounded-lg border p-4">
                                <p className="text-sm font-medium">{answer.question_text || `Answer ${i + 1}`}</p>
                                <p className="mt-3 whitespace-pre-wrap text-sm text-muted-foreground">
                                  {answer.student_answer || answer.answer || 'No answer stored.'}
                                </p>
                              </div>
                            ))}
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  )}

                  {!showTranscript && !showWrittenAnswers && (
                    <p className="text-sm text-muted-foreground">No content stored for this exam mode.</p>
                  )}
                </div>
              </TabsContent>

              {/* ── Reclamations tab ── */}
              <TabsContent value="contestations" className="mt-0 flex-1 overflow-y-auto">
                <div className="p-6">
                  <EvaluationContestationQueue
                    reEvalRequests={reEvalRequests}
                    questions={questions}
                    isTeacherOwner={true}
                    onChanged={reload}
                  />
                </div>
              </TabsContent>
            </Tabs>
          ) : null}
        </div>

        {/* Footer */}
        {attempt && (
          <div className="border-t px-6 py-3">
            <Button asChild variant="outline" size="sm">
              <Link href={`/dashboard/exams/attempts/${attempt.id}`}>
                Open full attempt page
                <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
              </Link>
            </Button>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
