# Content annotations — local validation, 2026-10-28

Implemented the approved independent page-content annotation flow. Natural text selection opens an annotation without activating review mode. `annotations.json` and per-annotation conversation snapshots remain separate from original comments and batches. The current working tree is the implementation under review; no release, install or consumer upgrade was performed.

## Verification

| Check | Result |
| --- | --- |
| `PYTHONPATH=runtime python3 -m unittest discover -s tests -p 'test_*.py'` | 172 tests passed, 117.276 seconds, final run |
| `PYTHONPATH=runtime python3 tests/test_annotations_browser.py` | 36 annotation browser assertions passed; also included in discovery |
| `ruby tests/browser/verify.rb` | 29 original review assertions passed |
| `ruby tests/browser/verify-attachments.rb` | 13 attachment assertions passed |
| `ruby tests/browser/verify-shared.rb` | 9 shared-review assertions passed |
| `node --check runtime/review.js`, Python compilation and `git diff --check` | Passed |
| Retained synthetic demo | 12 checks passed: selection, streaming, completion, evidence and refresh without repeated execution |

The annotation browser checks cover native mouse selection, cross-inline/reverse/multiline quotes, IME, independent counters, screenshot/image evidence, persistent queue and same-thread replies, failed/stopped/retried turns, lost-response confirmation, draft/focus preservation, keyboard and narrow layout, stale/ambiguous quotes, shared/offline exclusion, and an offline HTML export containing inert script-closing text.

Independent code review identified two defects, both fixed and re-reviewed: initial request confirmation after a newer `changed` record, and a legacy follow-up submitted while an annotation owns the execution lock. Dedicated regressions verify no stale overwrite, duplicate execution or stranded accepted legacy message. A busy legacy follow-up now returns a conflict before inbox persistence and retains its retry path.

Evidence is intentionally untracked under `artifacts/`: `annotations-full-unittest-final.log`, `annotations-legacy-browser.log`, `annotations-attachments-browser.log`, `annotations-shared-browser.log`, `validation-annotations/results.json`, and `annotation-demo/browser-verification.json` with desktop screenshots. All pages, records and protocol messages used for validation are synthetic; Chrome runs headlessly in isolated profiles.

## Limits

Agent transport, prompts, progress and recovery were checked with a protocol substitute. No real model job was dispatched; real-model intent accuracy and actual consumer modifications are not established by these results. Local interaction verification is separate from visual acceptance and production readiness. Formal consumer data, installed releases, running consumer services and historical tasks were not changed.

html2canvas and its isolation patch/license remain unchanged. Dependency SHA-256: `e13cf4fb0919313c321783fb67b51b18dd0e7e90d33ba9fc50706278f070d363`; license SHA-256: `934c3e7d2b010f3eef0b7fa06899b73e4b82c296f898490958bd5c42654c459c`.
