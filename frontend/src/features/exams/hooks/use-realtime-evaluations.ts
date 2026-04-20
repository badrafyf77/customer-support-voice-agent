'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchEvaluations, fetchExamContext } from '../lib/client';
import type { EvaluationsResponse, ExamContextResponse } from '../types';
import { createClient } from '@/utils/supabase/client';

export function useRealtimeEvaluations() {
  const supabase = useMemo(() => createClient(), []);
  const [context, setContext] = useState<ExamContextResponse | null>(null);
  const [evaluationsResponse, setEvaluationsResponse] = useState<EvaluationsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const refreshTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadEvaluations = useCallback(
    async (refreshOnly = false) => {
      if (refreshOnly) {
        setIsRefreshing(true);
      } else {
        setIsLoading(true);
      }

      try {
        const [nextContext, nextEvaluations] = await Promise.all([fetchExamContext(), fetchEvaluations()]);
        setContext(nextContext);
        setEvaluationsResponse(nextEvaluations);
        setErrorMessage(null);
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : 'Unable to load evaluations.');
      } finally {
        if (refreshOnly) {
          setIsRefreshing(false);
        } else {
          setIsLoading(false);
        }
      }
    },
    [],
  );

  const scheduleRefresh = useCallback(() => {
    if (refreshTimeoutRef.current) {
      clearTimeout(refreshTimeoutRef.current);
    }

    refreshTimeoutRef.current = setTimeout(() => {
      void loadEvaluations(true);
    }, 250);
  }, [loadEvaluations]);

  useEffect(() => {
    void loadEvaluations(false);
  }, [loadEvaluations]);

  useEffect(() => {
    const channel = supabase
      .channel('evaluations-dashboard')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'exam_attempts' }, scheduleRefresh)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'exam_question_results' }, scheduleRefresh)
      .on('postgres_changes', { event: '*', schema: 'public', table: 're_eval_requests' }, scheduleRefresh)
      .subscribe();

    return () => {
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current);
      }
      void supabase.removeChannel(channel);
    };
  }, [scheduleRefresh, supabase]);

  return {
    context,
    evaluationsResponse,
    isLoading,
    isRefreshing,
    errorMessage,
    reload: () => loadEvaluations(true),
  };
}
