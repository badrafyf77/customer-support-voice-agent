'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ORAL_EXAM_FINISH_TIMEOUT_MS, ORAL_EXAM_SERVER_READY_TIMEOUT_MS } from '../constants';
import { queueAttemptEvaluation } from '../lib/client';
import { useAudioCapture } from './use-audio-capture';
import { useWebcam } from './use-webcam';
import { useExamWebSocket } from './use-exam-websocket';

type FinishState = { state: 'idle' } | { state: 'success' } | { state: 'error'; error: string } | { state: 'timeout' };

interface UseLiveOralExamSessionOptions {
  serverUrl: string;
  examId: string;
  attemptId: string;
  userId?: string;
}

function waitForServerReady(isReadyRef: { current: boolean }) {
  return new Promise<void>((resolve, reject) => {
    const startedAt = Date.now();

    const checkStatus = () => {
      if (isReadyRef.current) {
        resolve();
        return;
      }

      if (Date.now() - startedAt >= ORAL_EXAM_SERVER_READY_TIMEOUT_MS) {
        reject(new Error('The oral exam server took too long to become ready.'));
        return;
      }

      window.setTimeout(checkStatus, 100);
    };

    checkStatus();
  });
}

export function useLiveOralExamSession({ serverUrl, examId, attemptId, userId }: UseLiveOralExamSessionOptions) {
  const [isRecording, setIsRecording] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [isFinishing, setIsFinishing] = useState(false);
  const [showFinishDialog, setShowFinishDialog] = useState(false);
  const [finishState, setFinishState] = useState<FinishState>({ state: 'idle' });

  const isReadyRef = useRef(false);
  const isTtsPlayingRef = useRef(false);
  const finishTimeoutRef = useRef<number | null>(null);
  const handledFinishMessageIdRef = useRef<string | null>(null);

  const {
    isConnected,
    isReady,
    serverStatus,
    statusMessage,
    messages,
    connect,
    disconnect,
    sendAudioData,
    sendMessage,
    stopTts,
    isTtsPlaying,
  } = useExamWebSocket(serverUrl, { userId, examId, attemptId });

  const { stream: webcamStream, startWebcam, stopWebcam, error: webcamError } = useWebcam();
  const { startCapture, stopCapture } = useAudioCapture(sendAudioData, () => isTtsPlayingRef.current);

  useEffect(() => {
    isReadyRef.current = isReady;
  }, [isReady]);

  useEffect(() => {
    isTtsPlayingRef.current = isTtsPlaying;
  }, [isTtsPlaying]);

  const clearFinishTimeout = useCallback(() => {
    if (finishTimeoutRef.current != null) {
      window.clearTimeout(finishTimeoutRef.current);
      finishTimeoutRef.current = null;
    }
  }, []);

  const stopMediaCapture = useCallback(() => {
    stopWebcam();
    stopCapture();
    setIsRecording(false);
  }, [stopCapture, stopWebcam]);

  const stopSession = useCallback(() => {
    clearFinishTimeout();
    handledFinishMessageIdRef.current = null;
    stopTts();
    disconnect();
    stopMediaCapture();
    setIsFinishing(false);
    setShowFinishDialog(false);
  }, [clearFinishTimeout, disconnect, stopMediaCapture, stopTts]);

  const startSession = useCallback(async () => {
    setIsStarting(true);
    setIsFinishing(false);
    handledFinishMessageIdRef.current = null;
    setFinishState({ state: 'idle' });

    try {
      await connect();
      await waitForServerReady(isReadyRef);
      await startWebcam();
      await startCapture();
      setIsRecording(true);
    } finally {
      setIsStarting(false);
    }
  }, [connect, startCapture, startWebcam]);

  const confirmFinish = useCallback(() => {
    setShowFinishDialog(false);
    setIsFinishing(true);
    setFinishState({ state: 'idle' });

    stopTts();
    stopMediaCapture();
    sendMessage({ type: 'finish_exam' });

    clearFinishTimeout();
    finishTimeoutRef.current = window.setTimeout(() => {
      setIsFinishing(false);
      disconnect();
      setFinishState({ state: 'timeout' });
    }, ORAL_EXAM_FINISH_TIMEOUT_MS);
  }, [clearFinishTimeout, disconnect, sendMessage, stopMediaCapture, stopTts]);

  useEffect(() => {
    if (serverStatus !== 'evaluating' && serverStatus !== 'finishing') {
      return;
    }

    setIsFinishing(true);
    stopTts();
    stopMediaCapture();
  }, [serverStatus, stopMediaCapture, stopTts]);

  useEffect(() => {
    const finishMessage = [...messages].reverse().find((message) => message.finishComplete);
    if (!finishMessage) {
      return;
    }

    if (handledFinishMessageIdRef.current === finishMessage.id) {
      return;
    }

    handledFinishMessageIdRef.current = finishMessage.id;
    const finalizeFinish = async () => {
      clearFinishTimeout();
      stopTts();
      stopMediaCapture();
      disconnect();

      if (finishMessage.success) {
        const resolvedAttemptId = (finishMessage.attemptId || attemptId || '').trim();
        const resolvedExamId = (finishMessage.examId || examId || '').trim();

        if (!resolvedAttemptId) {
          setIsFinishing(false);
          setFinishState({
            state: 'error',
            error: 'The oral exam was submitted, but no attempt id was available to start evaluation.',
          });
          return;
        }

        try {
          await queueAttemptEvaluation(resolvedAttemptId, {
            examId: resolvedExamId || undefined,
          });
        } catch (triggerError) {
          setIsFinishing(false);
          setFinishState({
            state: 'error',
            error:
              triggerError instanceof Error
                ? triggerError.message
                : 'The oral exam was submitted, but the evaluator could not be started automatically.',
          });
          return;
        }

        setIsFinishing(false);
        setFinishState({ state: 'success' });
        return;
      }

      setIsFinishing(false);
      setFinishState({
        state: 'error',
        error: finishMessage.error || 'Failed to finish the oral exam session.',
      });
    };

    void finalizeFinish();
  }, [attemptId, clearFinishTimeout, disconnect, examId, messages, stopMediaCapture, stopTts]);

  useEffect(() => {
    return () => {
      clearFinishTimeout();
    };
  }, [clearFinishTimeout]);

  return {
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
    openFinishDialog: () => setShowFinishDialog(true),
    closeFinishDialog: () => setShowFinishDialog(false),
    startSession,
    stopSession,
    confirmFinish,
  };
}
