# Veridex Frontend

This frontend is the main web product for Veridex. It handles the teacher and student experience around exam creation, enrollment, attempt management, oral exam rooms, and result review.

## What This App Is Responsible For

The frontend provides:

- authentication-aware teacher and student flows
- exam creation and exam management screens
- student join flows using a join code
- exam attempt pages and oral exam room UI
- dashboard views for attempts, feedback, and scores
- Next.js API routes that coordinate with Supabase
- Next.js API routes that trigger the evaluator agent after oral completion

It is not the speech engine itself. Live oral exam audio is handled by the separate backend in `../backend/ExaminerAgent`.

## Product Capabilities

With the current frontend, you can:

- create `oral`, `written`, and `hybrid` exams
- configure title, subject, duration, question count, and difficulty
- define rubric criteria and evaluation settings
- publish exams and let students join them
- start, resume, and review private student attempts
- connect the oral exam room to the realtime voice backend
- show transcripts and evaluation state while an oral exam is running

## Frontend Architecture

```text
Browser UI
  -> Next.js App Router pages
  -> feature hooks and components
  -> Next.js API routes
  -> Supabase

Live oral room
  -> WebSocket connection
  -> Realtime voice backend
  -> Supabase-backed attempt persistence
```

### Main layers

- `src/app`: app routes and API route handlers
- `src/features/exams`: exam-domain UI, hooks, client helpers, types, and server logic
- `src/components`: shared UI, dashboard, marketing, layout, and form components
- `src/utils/supabase`: Supabase client/server helpers
- `supabase/`: local Supabase config, migrations, and seed data

## Important Exam Flows

### Teacher flow

- create exam
- configure rubric and evaluation settings
- publish exam
- review attempts and outcomes

### Student flow

- join exam
- start an attempt
- enter the live oral exam room if the exam is oral or hybrid
- complete the attempt
- view results when available

## Important Files And Entry Points

- `src/features/exams/server/exam-service.ts`: core exam domain service logic
- `src/features/exams/components/exam-workspace.tsx`: main exam workspace UI
- `src/features/exams/components/live-oral-exam-room.tsx`: live oral exam room
- `src/features/exams/hooks/use-live-oral-exam-session.ts`: oral room orchestration on the client
- `src/features/exams/hooks/use-exam-websocket.ts`: realtime WebSocket communication
- `src/app/api/exams`: API endpoints for exam actions
- `src/app/dashboard/exams`: dashboard pages for exams and attempts

## Data Model The Frontend Depends On

The frontend assumes the exam domain defined in Supabase:

- `profiles`
- `exams`
- `exam_rubric_criteria`
- `exam_enrollments`
- `exam_attempts`

Those tables are created in:

- `supabase/migrations/20260404000003_veridex_exam_domain.sql`

## Local Development

### 1. Install dependencies

```bash
npm install
```

### 2. Configure environment

Copy the example file:

```bash
cp .env.local.example .env.local
```

Important variables:

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `NEXT_PUBLIC_SITE_URL`
- `NEXT_PUBLIC_EXAM_SERVER_URL`
- `EVALUATOR_AGENT_BASE_URL`
- `EXAM_GENERATOR_URL`

Optional billing variables:

- `NEXT_PUBLIC_PADDLE_ENV`
- `PADDLE_API_KEY`
- `PADDLE_NOTIFICATION_WEBHOOK_SECRET`
- `NEXT_PUBLIC_PADDLE_CLIENT_TOKEN`

### 3. Start the frontend

```bash
npm run dev
```

Default URL:

- `http://162.243.59.37:3000`

### 4. Connect to the oral exam backend

The live oral room depends on `../backend/ExaminerAgent`.
Automatic evaluator triggering depends on `../backend/EvaluatorAgent`.

Set `NEXT_PUBLIC_EXAM_SERVER_URL` correctly for the backend stack you are using:

- `ws://162.243.59.37:8080` for the examiner-agent Docker stack (vLLM or OpenAI mode)
- `http://162.243.59.37:8090` for evaluator trigger API calls from Next.js routes
- `http://162.243.59.37:8001` for exam generator API calls from Next.js routes

This distinction matters because the default backend compose file maps the app container to port `8080`, not `8000`.

## How The Frontend Talks To The Backend

### Supabase

Used for:

- auth
- profiles
- exams
- enrollments
- attempts
- rubric data

### Realtime voice backend

Used for:

- oral exam session startup
- streaming transcript updates
- Veridex voice responses
- automatic oral-exam completion and evaluation

### Evaluator agent backend

Used for:

- post-submission oral attempt evaluation triggers
- LangGraph-based evaluator workflows (placeholder scaffold in current repo state)

## Repository Notes

- The exam platform is the main product direction.
- Some onboarding, marketing, and billing pages still exist in the app.
- The oral exam room is tightly coupled to the backend speech service, so frontend-only changes often need backend awareness.

## Related Docs

- [Project README](../README.md)
- [Examiner-agent backend README](../backend/ExaminerAgent/README.md)
