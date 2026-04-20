'use client';

import { useState } from 'react';
import { CheckCircle2, LoaderIcon, Mic, RotateCcw, ShieldCheck, Square } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useVoiceRecorder } from '../hooks/use-voice-recorder';
import { uploadVoiceReference } from '../lib/voice-verification';

interface VoiceEnrollmentCardProps {
  userId: string;
  serverUrl?: string;
  onEnrolled: () => void;
}

const MIN_DURATION_MS = 3000;
const PROMPT =
  'Please read this sentence aloud: "I confirm I am the student taking this exam and this is my voice."';

function formatDuration(ms: number) {
  return `${Math.floor(ms / 1000)}s`;
}

export function VoiceEnrollmentCard({ userId, serverUrl, onEnrolled }: VoiceEnrollmentCardProps) {
  const recorder = useVoiceRecorder();
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const tooShort = !!recorder.recordedBlob && recorder.durationMs < MIN_DURATION_MS;

  const handleUpload = async () => {
    if (!recorder.recordedBlob) return;
    if (recorder.durationMs < MIN_DURATION_MS) {
      setUploadError('Recording is too short — please record at least 3 seconds.');
      return;
    }

    setIsUploading(true);
    setUploadError(null);
    try {
      await uploadVoiceReference({ userId, audioBlob: recorder.recordedBlob, serverUrl });
      onEnrolled();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : 'Upload failed. Please try again.');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <Card className="border-orange-500/40 bg-orange-500/5">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-orange-500" />
          Voice Enrollment Required
        </CardTitle>
        <CardDescription>
          Record your voice once. This fingerprint is stored permanently on your account and used to verify
          your identity during all future oral exams — the system cannot be fooled by a substitute.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-md border border-dashed border-border bg-muted/40 p-4 text-sm">
          <p className="font-medium">Read this aloud (at least 3 seconds):</p>
          <p className="mt-1 text-muted-foreground">{PROMPT}</p>
        </div>

        {!recorder.isSupported ? (
          <Alert variant="destructive">
            <AlertTitle>Recording not supported</AlertTitle>
            <AlertDescription>Your browser does not support the MediaRecorder API. Use a Chromium-based browser.</AlertDescription>
          </Alert>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          {!recorder.isRecording && !recorder.recordedBlob ? (
            <Button onClick={recorder.start} disabled={!recorder.isSupported || isUploading}>
              <Mic className="mr-2 h-4 w-4" />
              Start Recording
            </Button>
          ) : null}

          {recorder.isRecording ? (
            <Button onClick={recorder.stop} variant="destructive">
              <Square className="mr-2 h-4 w-4" />
              Stop ({formatDuration(recorder.durationMs)})
            </Button>
          ) : null}

          {recorder.recordedBlob && !recorder.isRecording ? (
            <>
              <Badge variant="outline">Recorded {formatDuration(recorder.durationMs)}</Badge>
              <Button
                onClick={() => {
                  recorder.reset();
                  setUploadError(null);
                }}
                variant="ghost"
                size="sm"
              >
                <RotateCcw className="mr-2 h-4 w-4" />
                Re-record
              </Button>
              <Button onClick={handleUpload} disabled={isUploading || tooShort}>
                {isUploading ? (
                  <>
                    <LoaderIcon className="mr-2 h-4 w-4 animate-spin" />
                    Saving…
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="mr-2 h-4 w-4" />
                    Save Voice Fingerprint
                  </>
                )}
              </Button>
            </>
          ) : null}
        </div>

        {recorder.recordedBlob && !recorder.isRecording ? (
          <audio controls className="w-full" src={URL.createObjectURL(recorder.recordedBlob)} />
        ) : null}

        {recorder.error ? (
          <Alert variant="destructive">
            <AlertDescription>{recorder.error}</AlertDescription>
          </Alert>
        ) : null}

        {uploadError ? (
          <Alert variant="destructive">
            <AlertDescription>{uploadError}</AlertDescription>
          </Alert>
        ) : null}

        {tooShort ? (
          <Alert>
            <AlertDescription>The recording is too short — please record at least 3 seconds.</AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}
