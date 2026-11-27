# Roadmap

Songyul is a spare-time project. Golf is off-season here in winter, so the plan has two speeds: light prep in winter, data collection when the season opens.

The goal: label real swings with launch-monitor results (Garmin R10), train a model on them, and give a short coaching comment after every shot. Later, without the R10.

## Winter (off-season)

- **Dataset export** — turn session logs into one row per swing: glove features, phases, pose per phase, club, and the paired R10 result.
- **Coach preview on recorded sessions** — replay past swings and let a language model (for example through the Claude API) turn the numbers into one or two spoken sentences. Tune tone, cost and delay without going to a range.
- **Gestures and screen** — tune double-tap (club dial) and four-tap (voice) from the new tap diagnostics log; record overlays in the in-app video.
- **v3 hardware** — XIAO on the forearm strap, external IMU on the back of the hand.
- **Replay tests** — run real recorded sessions through the page after every change, so behaviour is checked without a range visit.
- **Demo** — a browser demo that replays one real session, no glove needed.

## Season

| Milestone | What | Done when |
|---|---|---|
| M0 Stabilize | Use the current version at the range; tune tap thresholds from logs | Club change works first time in 9 of 10 tries |
| M1 Data | Record every session; keep misses too | 200+ R10-paired swings for each of 2–3 main clubs |
| M2 First model | Compare against a per-club average baseline (pose only, glove only, both); fat vs clean strike | Clearly better than the baseline on at least one target |
| M3 Coach (with R10) | One or two sentences after each shot, spoken, in English or Korean | Comments feel right more than half the time, at low cost |
| M4 Coach (without R10) | Estimate ball results from the glove; compare-to-your-good-shots coaching | Useful at a range with no launch monitor |
| M5 Other hands | A few other golfers try it | They can use it without help |
| M6 Share | Dataset (IMU, pose coordinates, R10 numbers; no voice audio) and model | Someone can rebuild the glove from this README |

Pull requests are closed for now; issues and ideas are welcome.
