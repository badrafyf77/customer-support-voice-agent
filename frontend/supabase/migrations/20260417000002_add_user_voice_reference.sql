-- Store a permanent per-user voice fingerprint on the profile.
-- Captured once during enrollment; reused across all oral exam attempts
-- to detect impersonation.
ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS voice_reference jsonb NOT NULL DEFAULT '{}'::jsonb;
