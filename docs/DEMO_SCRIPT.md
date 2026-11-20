# Three-minute operator walkthrough

## Before the walkthrough

1. Use the [controlled demo quickstart](../README.md#run-the-controlled-demo) for a fresh checkout. For the two-source presentation below, use the [system smoke-test runbook](SMOKE_TEST.md) and register the image ROI once. The controlled-only preparation already configures it.
2. Start one backend on `127.0.0.1:8000` with the stage's private `.env`. Start the frontend on port 5173 and open the dashboard. Confirm **Backend online**, **Events connected**, and an empty incident queue. [Local dashboard](http://localhost:5173)
3. Open **Operator access** and enter the private token before screen sharing. Select the first replay and bring up **Source provenance**. If available, keep a recording of a verified run open in a second tab.

## Presenter timing

| Time | Operator action and narration |
| --- | --- |
| 0:00–0:25 | Show the aerial source provenance and **REPLAY** label. “This is a local public-safety prototype. It processes approved prerecorded footage and asks an operator to review rule candidates.” |
| 0:25–0:55 | Start the aerial excerpt. Point to actual vehicle boxes and anonymous track IDs. After **End of replay**, show the empty queue. “This aerial excerpt verifies tracking and replay. It yielded zero incidents in our verification.” |
| 0:55–1:35 | Start **Controlled fixture - NASA still with two tracks**. “We placed two copies of a NASA still in a controlled replay to exercise the two rules with real inference.” Select the crowd candidate and show two tracks above the threshold of one for three frames. Select the zone candidate and point to the highlighted image ROI, scoped track ID, confirmation time, and thumbnail. |
| 1:35–2:15 | Show **Geolocation unavailable — image-space alert**. “The zone is defined in pixels. World location and measured location uncertainty are unavailable.” Acknowledge the zone candidate with the reason “Verified the controlled image-ROI crossing in the replay evidence.” Read the decision and reason in **Audit timeline**. |
| 2:15–2:45 | Stop the backend with Ctrl+C, let the browser show reconnecting, and restart against the same stage. Show **Events connected** and the saved review in the same tab. |
| 2:45–3:00 | Close with the local, offline CPU results and state what was measured. “The benchmark times a confirmation frame through the software pipeline. It provides no aerial accuracy or capture-to-alert measurement.” |

For a controlled-only presentation, use the opening to show the fixture provenance and explain the two animated copies of the NASA still. Continue with the controlled replay at 0:55.

## Fallback during the demonstration

Use the **27.76-second recorded verification of an earlier replay** in `data/evidence/prompt7/recorded-prior-verification.webm`. It captures the same verified sequence of real aerial replay, the controlled rules, review, backend shutdown, reconnect, and the restored audit. The screenshots in the same directory came from that rehearsal and include both candidate views and the audit after restart. Keep the recording identified as prerecorded while presenting it. Confirm the intended sharing rights before attaching the capture to the submission. [Capture verification log](STATUS.md#prompt-7-benchmark-and-submission-verification)
