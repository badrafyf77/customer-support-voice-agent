"""
Database module for loading Veridex profiles, exams, attempts, and rubric data from Supabase.
"""
import logging
from typing import Optional, Dict, Any, List
from supabase import create_client, Client

from core.config import get_env

logger = logging.getLogger(__name__)


class DatabaseClient:
    """
    Handles database operations for Veridex exam sessions.
    """

    def __init__(self):
        """Initialize Supabase client with environment variables."""
        supabase_url = get_env("SUPABASE_URL")
        supabase_key = get_env("SUPABASE_SERVICE_ROLE_KEY")

        if not supabase_url or not supabase_key:
            missing_names = []
            if not supabase_url:
                missing_names.append("SUPABASE_URL")
            if not supabase_key:
                missing_names.append("SUPABASE_SERVICE_ROLE_KEY")

            logger.warning(
                "⚠️ Supabase credentials not configured (%s). Exam context loading will be disabled.",
                ", ".join(missing_names),
            )
            self.client: Optional[Client] = None
            self.enabled = False
            return

        try:
            self.client = create_client(supabase_url, supabase_key)
            self.enabled = True
            logger.info("✅ Database client initialized successfully")
        except Exception as exc:
            logger.error(f"❌ Failed to initialize database client: {exc}")
            self.client = None
            self.enabled = False

    def get_app_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch the Veridex profile from the profiles table.
        """
        if not self.enabled or not self.client:
            logger.warning(f"⚠️ Database not enabled, cannot load Veridex profile for user {user_id}")
            return None

        try:
            response = self.client.table("profiles").select("*").eq("user_id", user_id).maybe_single().execute()

            if response.data:
                logger.info(f"✅ Loaded Veridex profile for user {user_id}: {response.data.get('full_name', 'Unknown')}")
                return response.data

            logger.warning(f"⚠️ No Veridex profile found for user {user_id}")
            return None
        except Exception as exc:
            logger.error(f"❌ Error loading Veridex profile for {user_id}: {exc}")
            return None

    def get_exam(self, exam_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch exam details.
        """
        if not self.enabled or not self.client:
            logger.warning(f"⚠️ Database not enabled, cannot load exam {exam_id}")
            return None

        try:
            response = self.client.table("exams").select("*").eq("id", exam_id).maybe_single().execute()

            if response.data:
                logger.info(f"✅ Loaded exam {exam_id}: {response.data.get('title', 'Unknown')}")
                return response.data

            logger.warning(f"⚠️ No exam found for {exam_id}")
            return None
        except Exception as exc:
            logger.error(f"❌ Error loading exam {exam_id}: {exc}")
            return None

    def get_exam_attempt(self, attempt_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch exam attempt details.
        """
        if not self.enabled or not self.client:
            logger.warning(f"⚠️ Database not enabled, cannot load attempt {attempt_id}")
            return None

        try:
            response = self.client.table("exam_attempts").select("*").eq("id", attempt_id).maybe_single().execute()

            if response.data:
                logger.info(
                    f"✅ Loaded exam attempt {attempt_id}: exam={response.data.get('exam_id', 'Unknown')} attempt={response.data.get('attempt_number', '?')}"
                )
                return response.data

            logger.warning(f"⚠️ No exam attempt found for {attempt_id}")
            return None
        except Exception as exc:
            logger.error(f"❌ Error loading exam attempt {attempt_id}: {exc}")
            return None

    def get_exam_rubric_criteria(self, exam_id: str) -> List[Dict[str, Any]]:
        """
        Fetch rubric criteria for an exam.
        """
        if not self.enabled or not self.client:
            logger.warning(f"⚠️ Database not enabled, cannot load rubric criteria for exam {exam_id}")
            return []

        try:
            response = (
                self.client.table("exam_rubric_criteria")
                .select("*")
                .eq("exam_id", exam_id)
                .order("display_order")
                .execute()
            )

            criteria = response.data or []
            logger.info(f"✅ Loaded {len(criteria)} rubric criteria for exam {exam_id}")
            return criteria
        except Exception as exc:
            logger.error(f"❌ Error loading rubric criteria for exam {exam_id}: {exc}")
            return []

    def update_attempt_transcript(self, attempt_id: str, conversation_history: list) -> bool:
        """
        Update an exam attempt with the latest conversation transcript.
        """
        if not self.enabled or not self.client:
            logger.warning(f"⚠️ Database not enabled, cannot update attempt {attempt_id}")
            return False

        try:
            self.client.table("exam_attempts").update({
                "conversation_history": conversation_history
            }).eq("id", attempt_id).execute()

            logger.info(f"✅ Updated transcript for exam attempt {attempt_id}")
            return True
        except Exception as exc:
            logger.error(f"❌ Error updating exam attempt transcript {attempt_id}: {exc}")
            return False

    def get_user_voice_reference(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the permanent voice fingerprint stored on a user's profile."""
        if not self.enabled or not self.client:
            return None

        try:
            response = (
                self.client.table("profiles")
                .select("voice_reference")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if response.data:
                payload = response.data.get("voice_reference") or {}
                return payload if isinstance(payload, dict) and payload.get("embedding") else None
            return None
        except Exception as exc:
            logger.error(f"❌ Error loading user voice reference for {user_id}: {exc}")
            return None

    def update_user_voice_reference(self, user_id: str, voice_reference: Dict[str, Any]) -> bool:
        """Persist the permanent per-user voice fingerprint on the profile."""
        if not self.enabled or not self.client:
            logger.warning(f"⚠️ Database not enabled, cannot store user voice reference for {user_id}")
            return False

        try:
            self.client.table("profiles").update({
                "voice_reference": voice_reference,
            }).eq("user_id", user_id).execute()
            logger.info(f"✅ Stored permanent voice reference for user {user_id}")
            return True
        except Exception as exc:
            logger.error(f"❌ Error saving user voice reference for {user_id}: {exc}")
            return False

    def update_voice_verification(self, attempt_id: str, verification: Dict[str, Any]) -> bool:
        """Persist the per-answer voice verification summary for an attempt."""
        if not self.enabled or not self.client:
            logger.warning(f"⚠️ Database not enabled, cannot store voice verification for {attempt_id}")
            return False

        try:
            self.client.table("exam_attempts").update({
                "voice_verification": verification,
            }).eq("id", attempt_id).execute()
            logger.info(f"✅ Stored voice verification summary for attempt {attempt_id}")
            return True
        except Exception as exc:
            logger.error(f"❌ Error saving voice verification for {attempt_id}: {exc}")
            return False

    def update_exam_attempt(self, attempt_id: str, update_data: Dict[str, Any]) -> bool:
        """
        Update an exam attempt with final oral-session metadata.
        """
        if not self.enabled or not self.client:
            logger.warning(f"⚠️ Database not enabled, cannot update attempt {attempt_id}")
            return False

        try:
            self.client.table("exam_attempts").update(update_data).eq("id", attempt_id).execute()
            logger.info(f"✅ Updated exam attempt {attempt_id}")
            return True
        except Exception as exc:
            logger.error(f"❌ Error updating exam attempt {attempt_id}: {exc}")
            return False


_db_client: Optional[DatabaseClient] = None


def get_database_client() -> DatabaseClient:
    """
    Get or create the global database client instance.
    """
    global _db_client
    if _db_client is None:
        _db_client = DatabaseClient()
    return _db_client


async def load_session_context(
    user_id: str | None,
    exam_id: str | None,
    attempt_id: str | None,
) -> Dict[str, Any]:
    """
    Load all database-backed context for a voice-agent session.

    The underlying Supabase calls are the same methods used by the previous
    server implementation; this function only gathers their results into a
    single context dictionary for agent builders.
    """
    db_client = get_database_client()
    user_profile = None
    exam = None
    exam_attempt = None
    rubric_criteria: list[dict[str, Any]] = []

    if user_id:
        user_profile = db_client.get_app_profile(user_id)

    if attempt_id:
        exam_attempt = db_client.get_exam_attempt(attempt_id)
        if exam_attempt:
            exam_id = exam_attempt.get("exam_id") or exam_id

    if exam_id:
        exam = db_client.get_exam(exam_id)
        rubric_criteria = db_client.get_exam_rubric_criteria(exam_id)

    return {
        "user_id": user_id,
        "exam_id": exam_id,
        "attempt_id": attempt_id,
        "user_profile": user_profile,
        "exam": exam,
        "exam_attempt": exam_attempt,
        "rubric_criteria": rubric_criteria,
    }
