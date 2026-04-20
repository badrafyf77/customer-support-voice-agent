'use client';

import { Activity, CheckCircle2, LoaderIcon, Mail, Sparkles, XCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { ExamAttempt } from '../types';

function readSummaryValue(summary: ExamAttempt['evaluator_summary'], key: string) {
  return (summary as Record<string, unknown> | null | undefined)?.[key];
}

export function EvaluationProgressCard({
  attempt,
  scoreSummaryPercentage,
}: {
  attempt: ExamAttempt;
  scoreSummaryPercentage?: number | null;
}) {
  const progressStatus = String(readSummaryValue(attempt.evaluator_summary, 'progress_status') || '').toLowerCase();
  const phase = String(readSummaryValue(attempt.evaluator_summary, 'phase') || '').trim();
  const questionsCompleted = Number(readSummaryValue(attempt.evaluator_summary, 'questions_completed') || 0);
  const questionsTotal = Number(readSummaryValue(attempt.evaluator_summary, 'questions_total') || 0);
  const publishStatus = String(readSummaryValue(attempt.evaluator_summary, 'publish_status') || '').trim();
  const notes = Array.isArray(readSummaryValue(attempt.evaluator_summary, 'notes'))
    ? (readSummaryValue(attempt.evaluator_summary, 'notes') as string[])
    : [];
  const runningScore =
    typeof attempt.overall_score === 'number'
      ? attempt.overall_score
      : typeof scoreSummaryPercentage === 'number'
        ? scoreSummaryPercentage
        : null;

  const isEvaluating =
    progressStatus === 'evaluating' || (attempt.status === 'submitted' && progressStatus !== 'completed');
  const isCompleted = attempt.status === 'evaluated' || progressStatus === 'completed';
  const isFailed = progressStatus === 'failed';

  if (!isEvaluating && !isCompleted && !isFailed) {
    return null;
  }

  return (
    <Card className="border-primary/20 bg-primary/5">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-xl">
              {isFailed ? (
                <XCircle className="h-5 w-5 text-destructive" />
              ) : isCompleted ? (
                <CheckCircle2 className="h-5 w-5 text-primary" />
              ) : (
                <LoaderIcon className="h-5 w-5 animate-spin text-primary" />
              )}
              {isCompleted
                ? 'Evaluation Complete'
                : isFailed
                  ? 'Evaluation Needs Attention'
                  : 'Evaluation Streaming Live'}
            </CardTitle>
            <CardDescription>
              {isCompleted
                ? 'Veridex has finished grading this attempt. Both the student and teacher can review the latest results.'
                : isFailed
                  ? 'The evaluator reported an issue while processing this attempt.'
                  : 'Question results and final totals will appear here as each evaluation step finishes.'}
            </CardDescription>
          </div>

          <div className="flex flex-wrap gap-2">
            {phase ? <Badge variant="outline">Phase: {phase}</Badge> : null}
            {questionsTotal > 0 ? (
              <Badge variant="secondary">
                {questionsCompleted}/{questionsTotal} items
              </Badge>
            ) : null}
            {publishStatus ? (
              <Badge variant={publishStatus === 'sent' ? 'default' : 'outline'}>
                <Mail className="mr-1 h-3.5 w-3.5" />
                {publishStatus}
              </Badge>
            ) : null}
          </div>
        </div>
      </CardHeader>

      <CardContent className="grid gap-4 md:grid-cols-3">
        <div className="rounded-lg border border-border/70 bg-background/80 p-4">
          <p className="flex items-center gap-2 text-sm font-medium">
            <Activity className="h-4 w-4 text-primary" />
            Attempt status
          </p>
          <p className="mt-2 text-sm text-muted-foreground">{attempt.status}</p>
        </div>

        <div className="rounded-lg border border-border/70 bg-background/80 p-4">
          <p className="flex items-center gap-2 text-sm font-medium">
            <Sparkles className="h-4 w-4 text-primary" />
            Running score
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            {runningScore != null ? `${runningScore}% current total` : 'Waiting for scored results'}
          </p>
        </div>

        <div className="rounded-lg border border-border/70 bg-background/80 p-4">
          <p className="text-sm font-medium">Latest notes</p>
          <p className="mt-2 text-sm text-muted-foreground">
            {notes.length > 0 ? notes[notes.length - 1] : 'Realtime progress updates will appear here.'}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
