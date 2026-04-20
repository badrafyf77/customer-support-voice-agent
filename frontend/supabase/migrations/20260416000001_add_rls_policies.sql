-- RLS policies for all application tables.
-- Required after switching from admin/service-role client to session client.

-- ─── Enable RLS ───────────────────────────────────────────────────────────────

ALTER TABLE public.profiles              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.exams                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.exam_enrollments      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.exam_attempts         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.exam_questions        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.exam_evaluations      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.exam_question_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.re_eval_requests      ENABLE ROW LEVEL SECURITY;

-- ─── profiles ────────────────────────────────────────────────────────────────

CREATE POLICY "profiles_select_own" ON public.profiles
  FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "profiles_insert_own" ON public.profiles
  FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "profiles_update_own" ON public.profiles
  FOR UPDATE TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- ─── exams ───────────────────────────────────────────────────────────────────

-- Teachers manage their own exams
CREATE POLICY "exams_select_teacher" ON public.exams
  FOR SELECT TO authenticated
  USING (teacher_user_id = auth.uid());

-- Students (and teachers) can see published/closed/archived exams (join by code, view results)
CREATE POLICY "exams_select_published" ON public.exams
  FOR SELECT TO authenticated
  USING (status IN ('published', 'closed', 'archived'));

CREATE POLICY "exams_insert_teacher" ON public.exams
  FOR INSERT TO authenticated
  WITH CHECK (teacher_user_id = auth.uid());

CREATE POLICY "exams_update_teacher" ON public.exams
  FOR UPDATE TO authenticated
  USING (teacher_user_id = auth.uid())
  WITH CHECK (teacher_user_id = auth.uid());

CREATE POLICY "exams_delete_teacher" ON public.exams
  FOR DELETE TO authenticated
  USING (teacher_user_id = auth.uid());

-- ─── exam_enrollments ────────────────────────────────────────────────────────

CREATE POLICY "enrollments_select_student" ON public.exam_enrollments
  FOR SELECT TO authenticated
  USING (student_user_id = auth.uid());

CREATE POLICY "enrollments_select_teacher" ON public.exam_enrollments
  FOR SELECT TO authenticated
  USING (exam_id IN (SELECT id FROM public.exams WHERE teacher_user_id = auth.uid()));

CREATE POLICY "enrollments_insert_student" ON public.exam_enrollments
  FOR INSERT TO authenticated
  WITH CHECK (student_user_id = auth.uid());

-- Teachers can update enrollment status (authorize / revoke)
CREATE POLICY "enrollments_update_teacher" ON public.exam_enrollments
  FOR UPDATE TO authenticated
  USING (exam_id IN (SELECT id FROM public.exams WHERE teacher_user_id = auth.uid()));

-- ─── exam_attempts ───────────────────────────────────────────────────────────

CREATE POLICY "attempts_select_student" ON public.exam_attempts
  FOR SELECT TO authenticated
  USING (student_user_id = auth.uid());

CREATE POLICY "attempts_select_teacher" ON public.exam_attempts
  FOR SELECT TO authenticated
  USING (exam_id IN (SELECT id FROM public.exams WHERE teacher_user_id = auth.uid()));

CREATE POLICY "attempts_insert_student" ON public.exam_attempts
  FOR INSERT TO authenticated
  WITH CHECK (student_user_id = auth.uid());

CREATE POLICY "attempts_update_student" ON public.exam_attempts
  FOR UPDATE TO authenticated
  USING (student_user_id = auth.uid())
  WITH CHECK (student_user_id = auth.uid());

-- Teachers may update attempts (e.g. cancel / override)
CREATE POLICY "attempts_update_teacher" ON public.exam_attempts
  FOR UPDATE TO authenticated
  USING (exam_id IN (SELECT id FROM public.exams WHERE teacher_user_id = auth.uid()));

-- ─── exam_questions ──────────────────────────────────────────────────────────

CREATE POLICY "questions_select_teacher" ON public.exam_questions
  FOR SELECT TO authenticated
  USING (exam_id IN (SELECT id FROM public.exams WHERE teacher_user_id = auth.uid()));

-- Students can read questions for exams they are enrolled in
CREATE POLICY "questions_select_enrolled" ON public.exam_questions
  FOR SELECT TO authenticated
  USING (exam_id IN (
    SELECT exam_id FROM public.exam_enrollments WHERE student_user_id = auth.uid()
  ));

CREATE POLICY "questions_insert_teacher" ON public.exam_questions
  FOR INSERT TO authenticated
  WITH CHECK (exam_id IN (SELECT id FROM public.exams WHERE teacher_user_id = auth.uid()));

CREATE POLICY "questions_update_teacher" ON public.exam_questions
  FOR UPDATE TO authenticated
  USING (exam_id IN (SELECT id FROM public.exams WHERE teacher_user_id = auth.uid()));

CREATE POLICY "questions_delete_teacher" ON public.exam_questions
  FOR DELETE TO authenticated
  USING (exam_id IN (SELECT id FROM public.exams WHERE teacher_user_id = auth.uid()));

-- ─── exam_evaluations ────────────────────────────────────────────────────────

CREATE POLICY "evaluations_select_teacher" ON public.exam_evaluations
  FOR SELECT TO authenticated
  USING (teacher_user_id = auth.uid());

CREATE POLICY "evaluations_select_student" ON public.exam_evaluations
  FOR SELECT TO authenticated
  USING (student_user_id = auth.uid());

-- Students insert their own evaluation record when finishing an attempt
CREATE POLICY "evaluations_insert_student" ON public.exam_evaluations
  FOR INSERT TO authenticated
  WITH CHECK (
    student_user_id = auth.uid() AND
    exam_id IN (SELECT exam_id FROM public.exam_enrollments WHERE student_user_id = auth.uid())
  );

CREATE POLICY "evaluations_update_teacher" ON public.exam_evaluations
  FOR UPDATE TO authenticated
  USING (teacher_user_id = auth.uid());

-- ─── exam_question_results ───────────────────────────────────────────────────

CREATE POLICY "question_results_select_teacher" ON public.exam_question_results
  FOR SELECT TO authenticated
  USING (attempt_id IN (
    SELECT id FROM public.exam_attempts
    WHERE exam_id IN (SELECT id FROM public.exams WHERE teacher_user_id = auth.uid())
  ));

CREATE POLICY "question_results_select_student" ON public.exam_question_results
  FOR SELECT TO authenticated
  USING (attempt_id IN (
    SELECT id FROM public.exam_attempts WHERE student_user_id = auth.uid()
  ));

-- Students insert results for their own attempts
CREATE POLICY "question_results_insert_student" ON public.exam_question_results
  FOR INSERT TO authenticated
  WITH CHECK (attempt_id IN (
    SELECT id FROM public.exam_attempts WHERE student_user_id = auth.uid()
  ));

CREATE POLICY "question_results_update_teacher" ON public.exam_question_results
  FOR UPDATE TO authenticated
  USING (attempt_id IN (
    SELECT id FROM public.exam_attempts
    WHERE exam_id IN (SELECT id FROM public.exams WHERE teacher_user_id = auth.uid())
  ));

-- ─── re_eval_requests ────────────────────────────────────────────────────────

CREATE POLICY "re_eval_select_student" ON public.re_eval_requests
  FOR SELECT TO authenticated
  USING (student_user_id = auth.uid());

CREATE POLICY "re_eval_select_teacher" ON public.re_eval_requests
  FOR SELECT TO authenticated
  USING (attempt_id IN (
    SELECT id FROM public.exam_attempts
    WHERE exam_id IN (SELECT id FROM public.exams WHERE teacher_user_id = auth.uid())
  ));

CREATE POLICY "re_eval_insert_student" ON public.re_eval_requests
  FOR INSERT TO authenticated
  WITH CHECK (student_user_id = auth.uid());

CREATE POLICY "re_eval_update_teacher" ON public.re_eval_requests
  FOR UPDATE TO authenticated
  USING (attempt_id IN (
    SELECT id FROM public.exam_attempts
    WHERE exam_id IN (SELECT id FROM public.exams WHERE teacher_user_id = auth.uid())
  ));
