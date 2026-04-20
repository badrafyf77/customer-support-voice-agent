-- Add per-attempt speaker verification fields.
--
-- voice_reference holds the ECAPA-TDNN embedding captured at exam start
-- (a JSON array of floats plus metadata). voice_verification holds the
-- per-answer similarity scores produced by the ExaminerAgent during the
-- session, so teachers can spot answers that look like a different speaker.

ALTER TABLE public.exam_attempts
  ADD COLUMN IF NOT EXISTS voice_reference jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS voice_verification jsonb NOT NULL DEFAULT '{}'::jsonb;
