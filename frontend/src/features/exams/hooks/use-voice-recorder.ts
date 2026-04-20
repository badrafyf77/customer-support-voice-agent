'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

export interface VoiceRecorderState {
  isSupported: boolean;
  isRecording: boolean;
  recordedBlob: Blob | null;
  durationMs: number;
  error: string | null;
}

export interface VoiceRecorderControls extends VoiceRecorderState {
  start: () => Promise<void>;
  stop: () => void;
  reset: () => void;
}

const PREFERRED_MIME_TYPES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/mp4',
];

function pickMimeType(): string | undefined {
  if (typeof window === 'undefined' || typeof window.MediaRecorder === 'undefined') {
    return undefined;
  }
  return PREFERRED_MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type));
}

export function useVoiceRecorder(): VoiceRecorderControls {
  const [isRecording, setIsRecording] = useState(false);
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);
  const [durationMs, setDurationMs] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [isSupported, setIsSupported] = useState(true);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const mimeTypeRef = useRef<string | undefined>(undefined);
  const startedAtRef = useRef<number>(0);
  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    setIsSupported(typeof window !== 'undefined' && typeof window.MediaRecorder !== 'undefined');
  }, []);

  const cleanup = useCallback(() => {
    if (intervalRef.current != null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setRecordedBlob(null);
    setDurationMs(0);
    chunksRef.current = [];

    if (!isSupported) {
      setError('Voice recording is not supported in this browser.');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const mimeType = pickMimeType();
      mimeTypeRef.current = mimeType;
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, {
          type: mimeTypeRef.current || 'audio/webm',
        });
        setRecordedBlob(blob);
        setIsRecording(false);
        cleanup();
      };

      recorder.onerror = (event) => {
        setError(`Recorder error: ${(event as ErrorEvent).message || 'unknown'}`);
        setIsRecording(false);
        cleanup();
      };

      startedAtRef.current = Date.now();
      recorder.start();
      setIsRecording(true);

      intervalRef.current = window.setInterval(() => {
        setDurationMs(Date.now() - startedAtRef.current);
      }, 200);
    } catch (recordError) {
      cleanup();
      setIsRecording(false);
      setError(
        recordError instanceof Error
          ? recordError.message
          : 'Could not access the microphone.',
      );
    }
  }, [cleanup, isSupported]);

  const stop = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    }
    if (intervalRef.current != null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    setRecordedBlob(null);
    setDurationMs(0);
    setError(null);
  }, []);

  useEffect(() => () => cleanup(), [cleanup]);

  return { isSupported, isRecording, recordedBlob, durationMs, error, start, stop, reset };
}
