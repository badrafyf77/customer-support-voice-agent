'use client';

import { useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, Clock3, LoaderIcon } from 'lucide-react';
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
import { Label } from '@/components/ui/label';
import { formatDateTime } from '../lib/formatters';
import { approveReEvalRequest, rejectReEvalRequest } from '../lib/client';
import type { ExamQuestion, ReEvalRequest } from '../types';

interface EvaluationContestationQueueProps {
  reEvalRequests: ReEvalRequest[];
  questions: ExamQuestion[];
  isTeacherOwner: boolean;
  onChanged?: () => Promise<void> | void;
}

export function EvaluationContestationQueue({
  reEvalRequests,
  questions,
  isTeacherOwner,
  onChanged,
}: EvaluationContestationQueueProps) {
  const [selectedRequest, setSelectedRequest] = useState<ReEvalRequest | null>(null);
  const [actionType, setActionType] = useState<'approve' | 'reject' | null>(null);
  const [teacherResponse, setTeacherResponse] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const pendingRequests = useMemo(
    () => reEvalRequests.filter((request) => request.status === 'pending').sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime()),
    [reEvalRequests],
  );

  if (!isTeacherOwner) {
    return null;
  }

  const questionById = new Map(questions.map((question) => [question.id, question]));

  const handleSubmit = async () => {
    if (!selectedRequest || !actionType) {
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      if (actionType === 'approve') {
        await approveReEvalRequest(selectedRequest.id, {
          teacherResponse: teacherResponse.trim() || undefined,
        });
        setSuccessMessage('Reclamation approved. Veridex re-checked the contested answer successfully.');
      } else {
        await rejectReEvalRequest(selectedRequest.id, {
          reason: teacherResponse.trim(),
        });
        setSuccessMessage('Reclamation rejected successfully.');
      }

      setSelectedRequest(null);
      setActionType(null);
      setTeacherResponse('');
      await onChanged?.();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to process this request.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Reclamation Queue</CardTitle>
        <CardDescription>
          Pending student reclamations. You can approve an AI re-check here, then still edit the evaluation manually in the Questions tab if needed.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {errorMessage ? (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Action failed</AlertTitle>
            <AlertDescription>{errorMessage}</AlertDescription>
          </Alert>
        ) : null}

        {successMessage ? (
          <Alert>
            <CheckCircle2 className="h-4 w-4" />
            <AlertTitle>Updated</AlertTitle>
            <AlertDescription>{successMessage}</AlertDescription>
          </Alert>
        ) : null}

        {pendingRequests.length === 0 ? (
          <div className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
            No pending reclamations on this evaluation right now.
          </div>
        ) : null}

        {pendingRequests.map((request) => {
          const question = request.question_id ? questionById.get(request.question_id) : null;
          return (
            <div key={request.id} className="rounded-xl border border-border bg-background/70 p-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="secondary">Pending</Badge>
                    <Badge variant="outline">
                      <Clock3 className="mr-1 h-3.5 w-3.5" />
                      {formatDateTime(request.created_at)}
                    </Badge>
                  </div>
                  <div>
                    <p className="font-semibold">{question?.question_text || 'Reclaimed question'}</p>
                    <p className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">{request.student_justification}</p>
                  </div>
                </div>

                <div className="flex shrink-0 gap-2">
                  <Button
                    onClick={() => {
                      setSelectedRequest(request);
                      setActionType('approve');
                      setTeacherResponse('');
                    }}
                  >
                    Approve
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setSelectedRequest(request);
                      setActionType('reject');
                      setTeacherResponse('');
                    }}
                  >
                    Reject
                  </Button>
                </div>
              </div>
            </div>
          );
        })}
      </CardContent>

      <Dialog open={selectedRequest != null && actionType != null} onOpenChange={(open) => !open && setSelectedRequest(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{actionType === 'approve' ? 'Approve reclamation' : 'Reject reclamation'}</DialogTitle>
            <DialogDescription>
              {actionType === 'approve'
                ? 'Optionally add a note before Veridex re-evaluates this reclaimed libre question.'
                : 'Tell the student why the original grade should stand.'}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor="teacher-response">{actionType === 'approve' ? 'Teacher note' : 'Reason'}</Label>
            <textarea
              id="teacher-response"
              value={teacherResponse}
              onChange={(event) => setTeacherResponse(event.target.value)}
              placeholder={actionType === 'approve' ? 'Approved. Please re-check this answer carefully.' : 'The original evaluation already reflects the rubric and reference answer.'}
              className="flex min-h-[180px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            />
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setSelectedRequest(null)} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button onClick={handleSubmit} disabled={isSubmitting || (actionType === 'reject' && teacherResponse.trim().length === 0)}>
              {isSubmitting ? <LoaderIcon className="mr-2 h-4 w-4 animate-spin" /> : null}
              {actionType === 'approve' ? 'Approve and run re-evaluation' : 'Reject reclamation'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
