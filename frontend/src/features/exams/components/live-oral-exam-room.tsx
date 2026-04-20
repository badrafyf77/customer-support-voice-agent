'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AlertTriangle, LoaderIcon, Mic, Square, Video } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DEFAULT_EXAM_SERVER_URL } from '../constants';
import { fetchExamAttempt, fetchExamContext } from '../lib/client';
import { getExamModeLabel } from '../lib/formatters';
import { checkVoiceReference } from '../lib/voice-verification';
import { useLiveOralExamSession } from '../hooks/use-live-oral-exam-session';
import { FinishExamDialog } from './finish-exam-dialog';
import { ExamEvaluationOverlay } from './exam-evaluation-overlay';
import { LiveExamHeader } from './live-exam-header';
import { TranscriptPanel } from './transcript-panel';
import { VideoPanel } from './video-panel';
import { VoiceEnrollmentCard } from './voice-enrollment-card';

interface LiveOralExamRoomProps {
  attemptId: string;
}

export function LiveOralExamRoom({ attemptId }: LiveOralExamRoomProps) {
  const router = useRouter();
  const [attemptResponse, setAttemptResponse] = useState<Awaited<ReturnType<typeof fetchExamAttempt>> | null>(null);
  const [context, setContext] = useState<Awaited<ReturnType<typeof fetchExamContext>> | null>(null);
  const [isLoadingContext, setIsLoadingContext] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  // null = check unavailable/skipped (don't gate), false = needs enrollment, true = enrolled
  const [hasVoiceRef, setHasVoiceRef] = useState<boolean | null>(null);

  useEffect(() => {
    const loadContext = async () => {
      try {
        const [nextAttemptResponse, nextContext] = await Promise.all([fetchExamAttempt(attemptId), fetchExamContext()]);
        setAttemptResponse(nextAttemptResponse);
        setContext(nextContext);

        const uid = nextContext?.context.user_id;
        if (uid) {
          // Voice check is best-effort — if the server is not set up, silently skip.
          checkVoiceReference(uid, DEFAULT_EXAM_SERVER_URL)
            .then((exists) => setHasVoiceRef(exists))
            .catch(() => setHasVoiceRef(null));
        }
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : 'Unable to load the oral exam room.');
      } finally {
        setIsLoadingContext(false);
      }
    };

    void loadContext();
  }, [attemptId]);

  const examId = attemptResponse?.exam.id || '';
  const userId = context?.context.user_id;
  const studentName = context?.context.profile?.full_name || 'Student';
  const examTitle = attemptResponse?.exam.title || 'Veridex Oral Exam';

  const {
    webcamStream,
    webcamError,
    messages,
    isConnected,
    isReady,
    statusMessage,
    isRecording,
    isStarting,
    isFinishing,
    showFinishDialog,
    finishState,
    openFinishDialog,
    closeFinishDialog,
    startSession,
    stopSession,
    confirmFinish,
  } = useLiveOralExamSession({
    serverUrl: DEFAULT_EXAM_SERVER_URL,
    examId,
    attemptId,
    userId,
  });
  const finishStatus = finishState.state;
  const finishError = finishState.state === 'error' ? finishState.error : null;

  useEffect(() => {
    if (finishStatus === 'timeout') {
      router.push(`/dashboard/exams/attempts/${attemptId}`);
      return;
    }

    if (finishStatus === 'error' && finishError) {
      window.alert(finishError);
      return;
    }

    if (finishStatus !== 'success') {
      return;
    }

    router.push(`/dashboard/exams/attempts/${attemptId}`);
  }, [attemptId, finishError, finishStatus, router]);

  const handleStart = async () => {
    try {
      await startSession();
    } catch (error) {
      console.error('Failed to start oral exam:', error);
      window.alert(
        error instanceof Error
          ? error.message
          : 'Failed to start the oral exam. Please check your permissions and server connection.',
      );
    }
  };

  const handleExit = () => {
    stopSession();
    router.push(`/dashboard/exams/attempts/${attemptId}`);
  };

  if (isLoadingContext) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <LoaderIcon className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (errorMessage || !attemptResponse || !context?.hasProfile || !context.role) {
    return (
      <Card>
        <CardContent className="py-10">
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Oral exam room unavailable</AlertTitle>
            <AlertDescription>{errorMessage || 'This attempt could not be opened.'}</AlertDescription>
          </Alert>

          <div className="mt-6">
            <Button asChild variant="outline">
              <Link href={`/dashboard/exams/attempts/${attemptId}`}>Back to attempt</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="relative flex h-full flex-col">
      <FinishExamDialog
        open={showFinishDialog}
        onOpenChange={(open) => {
          if (open) {
            openFinishDialog();
          } else {
            closeFinishDialog();
          }
        }}
        onConfirm={confirmFinish}
        title="Finish Oral Exam?"
        introText="Are you sure you want to finish this oral exam attempt?"
        followUpText="Veridex will evaluate the transcript against the teacher's rubric and you will not be able to continue this live session afterwards."
        checklistItems={[
          'Subject mastery evaluation',
          'Communication and clarity review',
          'Reasoning and accuracy scoring',
          'Private attempt storage under the shared exam',
        ]}
        confirmLabel="Yes, Finish Oral Exam"
      />

      <ExamEvaluationOverlay
        visible={isFinishing}
        message={statusMessage}
        title="Evaluating Your Oral Exam"
        fallbackMessage="Please wait while Veridex analyzes your oral exam attempt."
      />

      <LiveExamHeader
        examTitle={examTitle}
        isConnected={isConnected}
        onEnd={handleExit}
        subtitle={`Realtime ${getExamModeLabel(attemptResponse.exam.exam_mode).toLowerCase()} exam with an AI examiner.`}
        endLabel="Exit Oral Room"
      />

      <div className="mb-6 flex flex-wrap gap-3">
        <Badge variant="outline">{attemptResponse.exam.subject}</Badge>
        <Badge variant="outline">Attempt {attemptResponse.attempt.attempt_number}</Badge>
        <Badge variant="outline">{getExamModeLabel(attemptResponse.exam.exam_mode)}</Badge>
      </div>

      {hasVoiceRef === false && userId ? (
        <div className="mb-6">
          <VoiceEnrollmentCard
            userId={userId}
            serverUrl={DEFAULT_EXAM_SERVER_URL}
            onEnrolled={() => setHasVoiceRef(true)}
          />
        </div>
      ) : null}

      <div className="grid min-h-0 flex-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card className="flex h-full flex-col">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">Student Camera</CardTitle>

                <div className="flex items-center gap-2">
                  {isConnected && !isReady ? (
                    <Badge variant="secondary" className="animate-pulse">
                      <LoaderIcon className="mr-2 h-3 w-3 animate-spin" />
                      {statusMessage || 'Initializing...'}
                    </Badge>
                  ) : null}

                  {isRecording && isReady ? (
                    <Badge variant="destructive" className="animate-pulse">
                      <div className="mr-2 h-2 w-2 rounded-full bg-white" />
                      Recording
                    </Badge>
                  ) : null}
                </div>
              </div>
            </CardHeader>
            <CardContent className="min-h-0 flex-1">
              <VideoPanel
                candidateName={studentName}
                stream={webcamStream}
                isRecording={isRecording}
                error={webcamError}
                waitingTitle="Waiting for student camera..."
                permissionHint="Grant camera permissions when you start the oral exam."
                participantFallbackLabel="Student"
                assistantLabel="AI Examiner"
              />
            </CardContent>
          </Card>
        </div>

        <div className="lg:col-span-1">
          <Card className="flex h-full flex-col">
            <CardHeader>
              <CardTitle className="text-lg">Live Transcript</CardTitle>
            </CardHeader>
            <CardContent className="min-h-0 flex-1 p-0">
              <TranscriptPanel
                messages={messages}
                emptySecondaryText="Veridex will begin the oral exam after you start the session."
              />
            </CardContent>
          </Card>
        </div>
      </div>

      <Card className="mt-6">
        <CardContent className="py-4">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-3">
              {!isRecording ? (
                <Button onClick={handleStart} disabled={isStarting || !examId || hasVoiceRef === false} size="lg">
                  {isStarting ? (
                    <>
                      <LoaderIcon className="mr-2 h-4 w-4 animate-spin" />
                      {isConnected && !isReady ? statusMessage || 'Initializing...' : 'Starting...'}
                    </>
                  ) : (
                    <>
                      <Video className="mr-2 h-4 w-4" />
                      Start Oral Exam
                    </>
                  )}
                </Button>
              ) : (
                <Button onClick={stopSession} variant="secondary" size="lg">
                  <Square className="mr-2 h-4 w-4" />
                  Stop Capture
                </Button>
              )}

              <Button onClick={openFinishDialog} variant="outline" size="lg" disabled={!isConnected || isFinishing}>
                <AlertTriangle className="mr-2 h-4 w-4" />
                Finish & Evaluate
              </Button>
            </div>

            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <Mic className="h-4 w-4" />
              <span>{statusMessage || 'Veridex will lead the oral exam.'}</span>
            </div>
          </div>

          {finishState.state === 'error' ? (
            <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {finishState.error}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
