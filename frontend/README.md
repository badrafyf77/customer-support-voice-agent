# Voice Chat Frontend

Tiny Next/React frontend for starting a voice chat with the backend agent.

For the Lightning Darija backend, follow [the complete runbook](../backend/studio/RUNBOOK.md#5-connect-the-frontend-on-your-local-computer).
The backend runs on Studio, the frontend runs on localhost, and SSH forwards only
port 8080. Model weights and GPU dependencies stay on Studio.

```bash
npm run dev
```

Open `http://localhost:3000`.

There is no auth UI, no dashboard, and no database client in this frontend. The page only connects to the backend WebSocket `/ws` using the server URL entered on the page.


## Darija conversation checks

The transcript automatically chooses Arabic/Latin direction. The production UI
keeps the existing microphone and playback worklets and rejects canceled Darija
output using optional generation IDs. Reconnect starts a fresh transcript.
See [browser integration and Studio checklist](../backend/studio/BROWSER.md)
for the SSH tunnel, backend setup, local browser test harness and pending live
voice-quality/interruption checks.

```bash
npm test
npm run typecheck
npm run build
```

`npm run test:browser` requires the loopback harness and frontend described in
that checklist. It uses synthetic microphone input and deterministic fake model
output; it is not a live Darija quality result.
