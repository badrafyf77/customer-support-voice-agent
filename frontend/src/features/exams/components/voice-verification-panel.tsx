'use client';

import { AlertTriangle, ShieldAlert, ShieldCheck, ShieldX } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export interface VoiceVerificationCheck {
  answer_index?: number;
  score?: number | null;
  is_match?: boolean | null;
  skipped_reason?: string;
  transcript_excerpt?: string;
  checked_at?: string;
}

export interface VoiceVerificationSummary {
  total_checks?: number;
  flagged_count?: number;
  average_score?: number | null;
  min_score?: number | null;
  any_mismatch?: boolean;
}

export interface VoiceVerificationData {
  enabled?: boolean;
  has_reference?: boolean;
  threshold?: number;
  checks?: VoiceVerificationCheck[];
  summary?: VoiceVerificationSummary;
}

interface VoiceVerificationPanelProps {
  verification: VoiceVerificationData | null | undefined;
}

function formatScore(score: number | null | undefined): string {
  if (typeof score !== 'number') {
    return '—';
  }
  return `${(score * 100).toFixed(1)}%`;
}

function MatchBadge({ check, threshold }: { check: VoiceVerificationCheck; threshold: number }) {
  if (typeof check.score !== 'number') {
    if (check.skipped_reason === 'baseline_reference') {
      return (
        <Badge variant="secondary">
          <ShieldCheck className="mr-1 h-3 w-3" />
          Baseline
        </Badge>
      );
    }
    return <Badge variant="secondary">{check.skipped_reason || 'Skipped'}</Badge>;
  }
  if (check.is_match) {
    return (
      <Badge className="bg-green-600 hover:bg-green-600">
        <ShieldCheck className="mr-1 h-3 w-3" />
        Match {formatScore(check.score)}
      </Badge>
    );
  }
  return (
    <Badge variant="destructive">
      <ShieldX className="mr-1 h-3 w-3" />
      Mismatch {formatScore(check.score)} (≥ {formatScore(threshold)})
    </Badge>
  );
}

export function VoiceVerificationPanel({ verification }: VoiceVerificationPanelProps) {
  if (!verification || verification.enabled === false) {
    return null;
  }

  const hasReference = verification.has_reference === true;
  const checks = Array.isArray(verification.checks) ? verification.checks : [];
  const threshold = typeof verification.threshold === 'number' ? verification.threshold : 0.65;
  const summary = verification.summary || {};
  const flagged = summary.flagged_count || 0;
  const total = summary.total_checks || 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {flagged > 0 ? (
            <ShieldAlert className="h-5 w-5 text-destructive" />
          ) : (
            <ShieldCheck className="h-5 w-5 text-green-600" />
          )}
          Voice Verification
        </CardTitle>
        <CardDescription>
          ECAPA-TDNN speaker similarity between randomly sampled answers and the baseline voice
          captured from the student's first answer. Threshold: {formatScore(threshold)}.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!hasReference ? (
          <Alert>
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>No baseline voice captured</AlertTitle>
            <AlertDescription>
              The student's answers were too short to lock in a baseline embedding, so per-answer similarity
              scoring could not run.
            </AlertDescription>
          </Alert>
        ) : null}

        {hasReference ? (
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="rounded-md border border-border p-3">
              <p className="text-xs text-muted-foreground">Checks</p>
              <p className="text-lg font-semibold">{total}</p>
            </div>
            <div className="rounded-md border border-border p-3">
              <p className="text-xs text-muted-foreground">Average score</p>
              <p className="text-lg font-semibold">{formatScore(summary.average_score)}</p>
            </div>
            <div className="rounded-md border border-border p-3">
              <p className="text-xs text-muted-foreground">Flagged</p>
              <p className={`text-lg font-semibold ${flagged > 0 ? 'text-destructive' : ''}`}>{flagged}</p>
            </div>
          </div>
        ) : null}

        {flagged > 0 ? (
          <Alert variant="destructive">
            <ShieldAlert className="h-4 w-4" />
            <AlertTitle>{flagged} answer{flagged > 1 ? 's' : ''} flagged</AlertTitle>
            <AlertDescription>
              At least one answer's voice did not match the reference captured at exam start. Review the highlighted
              answers below before grading.
            </AlertDescription>
          </Alert>
        ) : null}

        {checks.length > 0 ? (
          <div className="space-y-2">
            {checks.map((check) => (
              <div
                key={`${check.answer_index ?? 0}-${check.checked_at ?? ''}`}
                className={`rounded-md border p-3 ${
                  check.is_match === false ? 'border-destructive/40 bg-destructive/5' : 'border-border'
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-sm font-medium">Answer #{(check.answer_index ?? 0) + 1}</div>
                  <MatchBadge check={check} threshold={threshold} />
                </div>
                {check.transcript_excerpt ? (
                  <p className="mt-2 text-xs italic text-muted-foreground">"{check.transcript_excerpt}"</p>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No per-answer verification entries recorded yet.</p>
        )}
      </CardContent>
    </Card>
  );
}
