'use client';

import { useCallback, useRef, useState } from 'react';
import { ORAL_EXAM_VIDEO_CONSTRAINTS } from '../constants';

export function useWebcam() {
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const startWebcam = useCallback(async () => {
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: ORAL_EXAM_VIDEO_CONSTRAINTS,
        audio: false,
      });

      streamRef.current = mediaStream;
      setStream(mediaStream);
      setError(null);
    } catch (webcamError) {
      const resolvedError = webcamError as Error;
      console.error('Error accessing webcam:', resolvedError);
      setError(resolvedError);
      throw resolvedError;
    }
  }, []);

  const stopWebcam = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setStream(null);
  }, []);

  return {
    stream,
    startWebcam,
    stopWebcam,
    error,
  };
}
