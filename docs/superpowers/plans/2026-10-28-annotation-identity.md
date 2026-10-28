# Inline annotation speaker identity

Follow-up to the authorized component publication and Charlee adoption: the user finds saved discussion roles unclear and explicitly requests `我：xxx` and `Agent：xxx`.

- Prefix the initial saved annotation and all user followups with `我：`; prefix assistant messages with `Agent：` on the same line as their content.
- Remove the separate Agent author row. Preserve the compact draft with no identity row, dates, actions, attachments, escaping, collapse/expand and message persistence.
- Match speaker presentation in the standalone annotation export while retaining its JSON payload and original message text exactly.
- Adapt existing exact-content assertions to query the message content span. Use focused synthetic visual checks rather than new redundant permanent tests for this markup-only change, and run documented regression checks.
- Deliver as a new fixed component version and update the current Charlee local integration under the existing publication/adoption request. Back up complete current data/jobs externally, wait for real tasks to finish naturally, retain old installed versions and preserve every original record. Do not edit an installed immutable release in place or exercise a real job to test labels.
