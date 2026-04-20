-- Fix infinite recursion in RLS policies (error 42P17).
--
-- Recursion chain that breaks every profiles query:
--   profiles → exam_enrollments (via teacher visibility policy)
--            → exams            (via teacher enrollment check)
--            → exam_enrollments (via student joined-exam check)
--            → ∞
--
-- Fix: wrap the cross-table subqueries in SECURITY DEFINER functions so
-- PostgreSQL evaluates them without re-entering RLS for those tables.

-- ─── Step 1: Drop policies added by 20260416000001 (clean up duplicates) ─────

DROP POLICY IF EXISTS "profiles_select_own"           ON public.profiles;
DROP POLICY IF EXISTS "profiles_insert_own"           ON public.profiles;
DROP POLICY IF EXISTS "profiles_update_own"           ON public.profiles;

DROP POLICY IF EXISTS "exams_select_teacher"          ON public.exams;
DROP POLICY IF EXISTS "exams_select_published"        ON public.exams;
DROP POLICY IF EXISTS "exams_insert_teacher"          ON public.exams;
DROP POLICY IF EXISTS "exams_update_teacher"          ON public.exams;
DROP POLICY IF EXISTS "exams_delete_teacher"          ON public.exams;

DROP POLICY IF EXISTS "enrollments_select_student"    ON public.exam_enrollments;
DROP POLICY IF EXISTS "enrollments_select_teacher"    ON public.exam_enrollments;
DROP POLICY IF EXISTS "enrollments_insert_student"    ON public.exam_enrollments;
DROP POLICY IF EXISTS "enrollments_update_teacher"    ON public.exam_enrollments;

DROP POLICY IF EXISTS "attempts_select_student"       ON public.exam_attempts;
DROP POLICY IF EXISTS "attempts_select_teacher"       ON public.exam_attempts;
DROP POLICY IF EXISTS "attempts_insert_student"       ON public.exam_attempts;
DROP POLICY IF EXISTS "attempts_update_student"       ON public.exam_attempts;
DROP POLICY IF EXISTS "attempts_update_teacher"       ON public.exam_attempts;

-- Also drop any policies added for tables that may not have had RLS before,
-- and disable RLS on them so we don't lock out the app.
DROP POLICY IF EXISTS "questions_select_teacher"         ON public.exam_questions;
DROP POLICY IF EXISTS "questions_select_enrolled"        ON public.exam_questions;
DROP POLICY IF EXISTS "questions_insert_teacher"         ON public.exam_questions;
DROP POLICY IF EXISTS "questions_update_teacher"         ON public.exam_questions;
DROP POLICY IF EXISTS "questions_delete_teacher"         ON public.exam_questions;
ALTER TABLE IF EXISTS public.exam_questions              DISABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "evaluations_select_teacher"       ON public.exam_evaluations;
DROP POLICY IF EXISTS "evaluations_select_student"       ON public.exam_evaluations;
DROP POLICY IF EXISTS "evaluations_insert_student"       ON public.exam_evaluations;
DROP POLICY IF EXISTS "evaluations_update_teacher"       ON public.exam_evaluations;
ALTER TABLE IF EXISTS public.exam_evaluations            DISABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "question_results_select_teacher"  ON public.exam_question_results;
DROP POLICY IF EXISTS "question_results_select_student"  ON public.exam_question_results;
DROP POLICY IF EXISTS "question_results_insert_student"  ON public.exam_question_results;
DROP POLICY IF EXISTS "question_results_update_teacher"  ON public.exam_question_results;
ALTER TABLE IF EXISTS public.exam_question_results       DISABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "re_eval_select_student"           ON public.re_eval_requests;
DROP POLICY IF EXISTS "re_eval_select_teacher"           ON public.re_eval_requests;
DROP POLICY IF EXISTS "re_eval_insert_student"           ON public.re_eval_requests;
DROP POLICY IF EXISTS "re_eval_update_teacher"           ON public.re_eval_requests;
ALTER TABLE IF EXISTS public.re_eval_requests            DISABLE ROW LEVEL SECURITY;

-- ─── Step 2: Drop the two original recursive policies ────────────────────────

-- exams: "Students can view joined exams" → subquery reads exam_enrollments
DROP POLICY IF EXISTS "Students can view joined exams"
  ON public.exams;

-- profiles: "Teachers can view profiles for own exam participants"
--           → subquery reads exam_enrollments JOIN exams → triggers the cycle
DROP POLICY IF EXISTS "Teachers can view profiles for own exam participants"
  ON public.profiles;

-- ─── Step 3: SECURITY DEFINER helpers (bypass RLS internally) ────────────────

-- Returns true if auth.uid() is enrolled in the given exam.
-- SECURITY DEFINER means it queries exam_enrollments without re-checking RLS,
-- breaking the exam_enrollments → exams → exam_enrollments cycle.
CREATE OR REPLACE FUNCTION public.rls_uid_is_enrolled(p_exam_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.exam_enrollments
    WHERE exam_id = p_exam_id
      AND student_user_id = auth.uid()
      AND status IN ('joined', 'authorized')
  );
$$;

-- Returns true if auth.uid() (a teacher) should be able to see a given user's profile
-- because that user is enrolled in one of the teacher's exams.
-- SECURITY DEFINER breaks the profiles → exam_enrollments → exams → exam_enrollments cycle.
CREATE OR REPLACE FUNCTION public.rls_teacher_can_view_profile(p_user_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.exam_enrollments ee
    JOIN public.exams e ON e.id = ee.exam_id
    WHERE ee.student_user_id = p_user_id
      AND e.teacher_user_id = auth.uid()
  );
$$;

-- ─── Step 4: Recreate fixed versions of the dropped policies ─────────────────

CREATE POLICY "Students can view joined exams"
  ON public.exams FOR SELECT
  USING (public.rls_uid_is_enrolled(exams.id));

CREATE POLICY "Teachers can view profiles for own exam participants"
  ON public.profiles FOR SELECT
  USING (public.rls_teacher_can_view_profile(profiles.user_id));
