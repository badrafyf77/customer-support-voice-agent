# Oral Exam Voice Agent Frontend

Tiny Next/React frontend for starting the oral exam voice agent.

```bash
npm run dev
```

Open `http://localhost:3000`.

There is no auth UI, no dashboard, and no database client in this frontend. The page only connects to the backend WebSocket `/ws` using the server URL, user ID, exam ID, and attempt ID entered on the page.
