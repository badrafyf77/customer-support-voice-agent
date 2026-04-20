'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchExamAttempt } from '../lib/client';
import type { ExamAttemptResponse } from '../types';
import { createClient } from '@/utils/supabase/client';

export function useRealtimeAttemptEvaluation(attemptId: string) {
  const supabase = useMemo(() => createClient(), []);
  const [attemptResponse, setAttemptResponse] = useState<ExamAttemptResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const refreshTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const refreshInFlightRef = useRef(false);

  const loadAttempt = useCallback(
    async (refreshOnly = false) => {
      if (refreshInFlightRef.current) {
        return;
      }

      refreshInFlightRef.current = true;

      if (refreshOnly) {
        setIsRefreshing(true);
      } else {
        setIsLoading(true);
      }

      try {
        const response = await fetchExamAttempt(attemptId);
        setAttemptResponse(response);
        setErrorMessage(null);
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : 'Unable to load this attempt.');
      } finally {
        if (refreshOnly) {
          setIsRefreshing(false);
        } else {
          setIsLoading(false);
        }

        refreshInFlightRef.current = false;
      }
    },
    [attemptId],
  );

  const scheduleRefresh = useCallback(() => {
    if (refreshTimeoutRef.current) {
      clearTimeout(refreshTimeoutRef.current);
    }

    refreshTimeoutRef.current = setTimeout(() => {
      void loadAttempt(true);
    }, 200);
  }, [loadAttempt]);

  useEffect(() => {
    void loadAttempt(false);
  }, [loadAttempt]);

  useEffect(() => {
    const channel = supabase
      .channel(`attempt-evaluation:${attemptId}`)
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'exam_attempts', filter: `id=eq.${attemptId}` },
        scheduleRefresh,
      )
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'exam_question_results', filter: `attempt_id=eq.${attemptId}` },
        scheduleRefresh,
      )
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 're_eval_requests', filter: `attempt_id=eq.${attemptId}` },
        scheduleRefresh,
      )
      .subscribe();

    return () => {
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current);
      }
      void supabase.removeChannel(channel);
    };
  }, [attemptId, scheduleRefresh, supabase]);

  useEffect(() => {
    const attempt = attemptResponse?.attempt;
    if (!attempt) {
      return;
    }

    const summary = (attempt.evaluator_summary as Record<string, unknown> | null | undefined) ?? null;
    const progressStatus = String(summary?.progress_status || '')
      .trim()
      .toLowerCase();
    const shouldPoll = attempt.status === 'submitted' || progressStatus === 'evaluating' || progressStatus === 'queued';

    if (!shouldPoll) {
      return;
    }

    const intervalHandle = setInterval(() => {
      void loadAttempt(true);
    }, 2500);

    return () => {
      clearInterval(intervalHandle);
    };
  }, [attemptResponse, loadAttempt]);

  return {
    attemptResponse,
    isLoading,
    isRefreshing,
    errorMessage,
    reload: () => loadAttempt(true),
  };
}
