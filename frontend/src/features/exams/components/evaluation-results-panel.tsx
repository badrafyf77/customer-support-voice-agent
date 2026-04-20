'use client';

import { useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, CircleDashed, LoaderIcon, MessageSquareWarning, PencilLine } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { formatDateTime, getScoreBadgeVariant } from '../lib/formatters';
import { adjustAttemptQuestion, createAttemptContestation } from '../lib/client';
import type { EvaluationQuestionResult, ExamQuestion, ReEvalRequest } from '../types';

interface EvaluationResultsPanelProps {
  attemptId: string;
  questions: ExamQuestion[];
  questionResults: EvaluationQuestionResult[];
  reEvalRequests: ReEvalRequest[];
  isStudentOwner: boolean;
  isTeacherOwner: boolean;
  canShowEvaluation: boolean;
  onChanged?: () => Promise<void> | void;
}

interface DisplayItem {
  id: string;
  question: ExamQuestion | null;
  result: EvaluationQuestionResult | null;
  title: string;
  orderLabel: string;
  typeLabel: string;
}

function getLatestRequestForQuestion(requests: ReEvalRequest[], questionId: string | null | undefined) {
  if (!questionId) {
    return null;
  }

  return [...requests]
    .filter((request) => request.question_id === questionId)
    .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())[0] || null;
}

export function EvaluationResultsPanel({
  attemptId,
  questions,
  questionResults,
  reEvalRequests,
  isStudentOwner,
  isTeacherOwner,
  canShowEvaluation,
  onChanged,
}: EvaluationResultsPanelProps) {
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [contestQuestion, setContestQuestion] = useState<DisplayItem | null>(null);
  const [contestJustification, setContestJustification] = useState('');
  const [adjustQuestion, setAdjustQuestion] = useState<DisplayItem | null>(null);
  const [adjustedScore, setAdjustedScore] = useState('');
  const [adjustmentComment, setAdjustmentComment] = useState('');
  const [isSubmittingContest, setIsSubmittingContest] = useState(false);
  const [isSubmittingAdjustment, setIsSubmittingAdjustment] = useState(false);

  const displayItems = useMemo<DisplayItem[]>(() => {
    const resultByQuestionId = new Map(questionResults.filter((result) => result.question_id).map((result) => [result.question_id!, result]));
    const itemsFromQuestions = questions.map((question) => ({
      id: question.id,
      question,
      result: resultByQuestionId.get(question.id) || null,
      title: question.question_text,
      orderLabel: `Question ${question.question_order}`,
      typeLabel: question.question_type.toUpperCase(),
    }));

    const extraResults = questionResults
      .filter((result) => !result.question_id || !resultByQuestionId.has(result.question_id))
      .map((result, index) => ({
        id: result.id,
        question: null,
        result,
        title: result.question_type === 'oral' ? 'Oral evaluation' : `Evaluated item ${index + 1}`,
        orderLabel: result.question_order ? `Question ${result.question_order}` : 'Holistic result',
        typeLabel: result.question_type.toUpperCase(),
      }));

    return [...itemsFromQuestions, ...extraResults].sort((left, right) => {
      const leftOrder = left.result?.question_order ?? left.question?.question_order ?? Number.MAX_SAFE_INTEGER;
      const rightOrder = right.result?.question_order ?? right.question?.question_order ?? Number.MAX_SAFE_INTEGER;
      return leftOrder - rightOrder;
    });
  }, [questionResults, questions]);

  const handleContestSubmit = async () => {
    if (!contestQuestion?.question) {
      return;
    }

    setIsSubmittingContest(true);
    setActionError(null);
    setActionSuccess(null);

    try {
      const response = await createAttemptContestation(attemptId, {
        questionId: contestQuestion.question.id,
        studentJustification: contestJustification.trim(),
      });
      setActionSuccess(response.message || 'Reclamation submitted successfully.');
      setContestQuestion(null);
      setContestJustification('');
      await onChanged?.();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Unable to submit the reclamation.');
    } finally {
      setIsSubmittingContest(false);
    }
  };

  const handleAdjustmentSubmit = async () => {
    if (!adjustQuestion?.question) {
      return;
    }

    const numericScore = Number(adjustedScore);
    if (!Number.isFinite(numericScore)) {
      setActionError('Adjusted score must be a valid number.');
      return;
    }

    if (adjustQuestion.result?.max_points != null && (numericScore < 0 || numericScore > adjustQuestion.result.max_points)) {
      setActionError(`Adjusted score must stay between 0 and ${adjustQuestion.result.max_points}.`);
      return;
    }

    setIsSubmittingAdjustment(true);
    setActionError(null);
    setActionSuccess(null);

    try {
      await adjustAttemptQuestion(attemptId, adjustQuestion.question.id, {
        adjustedScore: numericScore,
        comment: adjustmentComment.trim() || null,
      });
      setActionSuccess('Manual adjustment saved successfully.');
      setAdjustQuestion(null);
      setAdjustedScore('');
      setAdjustmentComment('');
      await onChanged?.();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Unable to adjust this question score.');
    } finally {
      setIsSubmittingAdjustment(false);
    }
  };

  if (!canShowEvaluation) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Question Results</CardTitle>
        <CardDescription>Each question result appears here as soon as it is written to Supabase.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {actionError ? (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Action failed</AlertTitle>
            <AlertDescription>{actionError}</AlertDescription>
          </Alert>
        ) : null}

        {actionSuccess ? (
          <Alert>
            <CheckCircle2 className="h-4 w-4" />
            <AlertTitle>Updated</AlertTitle>
            <AlertDescription>{actionSuccess}</AlertDescription>
          </Alert>
        ) : null}

        {displayItems.length === 0 ? (
          <div className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
            No question results have been written yet. They will appear here while the evaluation runs.
          </div>
        ) : null}

        {displayItems.map((item) => {
          const latestRequest = getLatestRequestForQuestion(reEvalRequests, item.question?.id ?? item.result?.question_id);
          const criteriaResults = item.result?.criteria_breakdown?.criteria_results || [];
          const canContest =
            isStudentOwner &&
            item.question?.question_type === 'libre' &&
            item.result != null &&
            latestRequest?.status !== 'pending';
          const canAdjust = isTeacherOwner && item.question != null && item.result != null;

          return (
            <div key={item.id} className="rounded-xl border border-border bg-background/70 p-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">{item.orderLabel}</Badge>
                    <Badge variant="secondary">{item.typeLabel}</Badge>
                    {item.result ? (
                      <Badge variant={getScoreBadgeVariant(item.result.effective_score)}>
                        {item.result.effective_score}/{item.result.max_points ?? 0}
                      </Badge>
                    ) : (
                      <Badge variant="outline">
                        <CircleDashed className="mr-1 h-3.5 w-3.5" />
                        Pending
                      </Badge>
                    )}
                    {item.result?.effective_source && item.result.effective_source !== 'original' ? (
                      <Badge variant="outline">{item.result.effective_source.replace('_', ' ')}</Badge>
                    ) : null}
                    {latestRequest ? <Badge variant={latestRequest.status === 'pending' ? 'secondary' : 'outline'}>{latestRequest.status}</Badge> : null}
                  </div>

                  <div>
                    <p className="text-base font-semibold">{item.title}</p>
                    {item.question?.question_type === 'qcm' && item.question.choices?.length ? (
                      <p className="mt-2 text-sm text-muted-foreground">Choices: {item.question.choices.join(' / ')}</p>
                    ) : null}
                  </div>

                  {item.result ? (
                    <div className="space-y-3 text-sm text-muted-foreground">
                      <p className="whitespace-pre-wrap">{item.result.effective_feedback}</p>
                      {item.result.student_answer ? (
                        <div>
                          <p className="font-medium text-foreground">Student answer</p>
                          <p className="mt-1 whitespace-pre-wrap">{item.result.student_answer}</p>
                        </div>
                      ) : null}
                      {item.result.correct_answer ? (
                        <div>
                          <p className="font-medium text-foreground">Reference answer</p>
                          <p className="mt-1 whitespace-pre-wrap">{item.result.correct_answer}</p>
                        </div>
                      ) : null}
                      {criteriaResults.length > 0 ? (
                        <div className="space-y-2">
                          <p className="font-medium text-foreground">Criteria breakdown</p>
                          {criteriaResults.map((criterion) => (
                            <div key={`${item.id}-${criterion.name}`} className="rounded-lg border border-border/70 p-3">
                              <div className="flex items-center justify-between gap-3">
                                <span className="font-medium text-foreground">{criterion.name}</span>
                                <Badge variant="outline">
                                  {criterion.score}/{criterion.max_score}
                                </Badge>
                              </div>
                              <p className="mt-2 whitespace-pre-wrap">{criterion.justification}</p>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <div className="text-sm text-muted-foreground">
                      <p>This question is still waiting for a result row from the evaluator.</p>
                    </div>
                  )}

                  {latestRequest ? (
                    <div className="rounded-lg border border-border/70 bg-muted/30 p-3 text-sm text-muted-foreground">
                      <p className="font-medium text-foreground">Reclamation activity</p>
                      <p className="mt-1 whitespace-pre-wrap">Student: {latestRequest.student_justification}</p>
                      {latestRequest.contestation_response ? (
                        <p className="mt-2 whitespace-pre-wrap">Response: {latestRequest.contestation_response}</p>
                      ) : null}
                      {latestRequest.teacher_response ? (
                        <p className="mt-2 whitespace-pre-wrap">Teacher: {latestRequest.teacher_response}</p>
                      ) : null}
                      <p className="mt-2 text-xs">Created {formatDateTime(latestRequest.created_at)}</p>
                    </div>
                  ) : null}
                </div>

                <div className="flex shrink-0 flex-col gap-2 lg:w-48">
                  {canContest ? (
                    <Button
                      variant="outline"
                      onClick={() => {
                        setContestQuestion(item);
                        setContestJustification('');
                      }}
                    >
                      <MessageSquareWarning className="mr-2 h-4 w-4" />
                      Send reclamation
                    </Button>
                  ) : null}

                  {canAdjust ? (
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setAdjustQuestion(item);
                        setAdjustedScore(String(item.result?.effective_score ?? ''));
                        setAdjustmentComment(item.result?.effective_source === 'teacher_adjusted' ? item.result?.effective_feedback || '' : '');
                      }}
                    >
                      <PencilLine className="mr-2 h-4 w-4" />
                      Adjust score
                    </Button>
                  ) : null}

                  {item.result == null ? (
                    <Button variant="ghost" disabled>
                      <LoaderIcon className="mr-2 h-4 w-4 animate-spin" />
                      Waiting
                    </Button>
                  ) : null}
                </div>
              </div>
            </div>
          );
        })}
      </CardContent>

      <Dialog open={contestQuestion != null} onOpenChange={(open) => !open && setContestQuestion(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Send a reclamation</DialogTitle>
            <DialogDescription>
              Explain why you believe this evaluated answer deserves a better score. Your teacher will receive the reclamation in the evaluation dashboard and, when email is configured, by email as well.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor="student-contestation">Why should this score be reviewed?</Label>
            <textarea
              id="student-contestation"
              value={contestJustification}
              onChange={(event) => setContestJustification(event.target.value)}
              placeholder="I covered the instability argument even though I used different phrasing..."
              className="flex min-h-[180px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            />
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setContestQuestion(null)} disabled={isSubmittingContest}>
              Cancel
            </Button>
            <Button onClick={handleContestSubmit} disabled={isSubmittingContest || contestJustification.trim().length === 0}>
              {isSubmittingContest ? <LoaderIcon className="mr-2 h-4 w-4 animate-spin" /> : null}
              Submit reclamation
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={adjustQuestion != null} onOpenChange={(open) => !open && setAdjustQuestion(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Adjust question score</DialogTitle>
            <DialogDescription>
              Apply a manual score adjustment for this question. The evaluation total will be recalculated immediately.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="adjusted-score">Adjusted score</Label>
              <Input
                id="adjusted-score"
                type="number"
                value={adjustedScore}
                onChange={(event) => setAdjustedScore(event.target.value)}
                min={0}
                max={adjustQuestion?.result?.max_points ?? undefined}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="adjustment-comment">Comment</Label>
              <textarea
                id="adjustment-comment"
                value={adjustmentComment}
                onChange={(event) => setAdjustmentComment(event.target.value)}
                placeholder="Explain why you are changing this score."
                className="flex min-h-[160px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setAdjustQuestion(null)} disabled={isSubmittingAdjustment}>
              Cancel
            </Button>
            <Button onClick={handleAdjustmentSubmit} disabled={isSubmittingAdjustment || adjustedScore.trim().length === 0}>
              {isSubmittingAdjustment ? <LoaderIcon className="mr-2 h-4 w-4 animate-spin" /> : null}
              Save adjustment
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
