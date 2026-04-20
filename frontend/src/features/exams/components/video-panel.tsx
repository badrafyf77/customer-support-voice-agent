'use client';

import { useEffect, useRef } from 'react';
import { Camera, User } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

interface VideoPanelProps {
  candidateName: string;
  stream: MediaStream | null;
  isRecording: boolean;
  error: Error | null;
  waitingTitle?: string;
  permissionHint?: string;
  participantFallbackLabel?: string;
  assistantLabel?: string;
}

export function VideoPanel({
  candidateName,
  stream,
  isRecording,
  error,
  waitingTitle = 'Waiting for camera...',
  permissionHint = 'Grant camera permissions when you start the oral exam.',
  participantFallbackLabel = 'Student',
  assistantLabel = 'AI Examiner',
}: VideoPanelProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (videoRef.current && stream) {
      videoRef.current.srcObject = stream;
    }
  }, [stream]);

  return (
    <div className="relative h-full min-h-[400px] w-full overflow-hidden rounded-lg border bg-muted">
      {stream ? (
        <video ref={videoRef} autoPlay playsInline muted className="h-full w-full scale-x-[-1] object-cover" />
      ) : (
        <div className="flex h-full w-full items-center justify-center bg-muted">
          <div className="text-center">
            {error ? (
              <>
                <Camera className="mx-auto mb-4 h-16 w-16 text-muted-foreground" />
                <p className="text-lg font-medium text-foreground">Camera unavailable</p>
                <p className="mt-2 text-sm text-muted-foreground">{error.message}</p>
              </>
            ) : (
              <>
                <User className="mx-auto mb-4 h-16 w-16 text-muted-foreground" />
                <p className="text-lg font-medium text-foreground">{waitingTitle}</p>
                <p className="mt-2 text-sm text-muted-foreground">{permissionHint}</p>
              </>
            )}
          </div>
        </div>
      )}

      <div className="absolute bottom-4 left-4">
        <Badge variant="secondary" className="bg-background/80 backdrop-blur-sm">
          <User className="mr-2 h-3 w-3" />
          {candidateName || participantFallbackLabel}
        </Badge>
      </div>

      <div className="absolute bottom-4 right-4">
        <Badge variant="default" className="bg-primary/80 backdrop-blur-sm">
          <div className={`mr-2 h-2 w-2 rounded-full ${isRecording ? 'animate-pulse bg-green-400' : 'bg-gray-400'}`} />
          {assistantLabel}
        </Badge>
      </div>
    </div>
  );
}
