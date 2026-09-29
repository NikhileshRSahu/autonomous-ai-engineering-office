
## Friendly run overview

The Control Room default view now leads with the user's goal rather than raw engineering metadata. It shows the selected run mode, objective, real stage states, total elapsed time, current-stage time, an empirical ETA/learning state, a plain-language “What's happening” card, and a persistent “Needs You” card.

Run modes are selected directly from the header: **Check & Report**, **Fast Audit**, **Complete Project**, **Fix Issues**, or **Custom**. The same backend run-mode implementation is used by the CLI.

The selected specialist opens on **Activity**. Raw observable work remains one click away under **Terminal**, with Files, Messages, Task, Evidence, Traces, and Model as advanced views. Model loading is described as a wait state; the UI never invents a load percentage when the runtime does not provide one.

When a permanent report exists, the overview exposes Open Report, report-folder path, evidence, and Replay actions. In browser-only mode the report-folder action reveals the safe local path rather than executing an arbitrary filesystem opener.
