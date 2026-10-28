# Content Annotations Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development to implement the bounded tasks. User approved implementation; no additional permission gate for the plan. Do not commit or publish.

**Goal:** Normal reading supports separate text annotations with automatic, persistent Agent conversations; existing review mode stays unchanged.

**Architecture:** Keep annotations in `annotations.json`, isolated from `comments.json`. Extend the existing Codex runner with per-annotation jobs and the same project lock; persist public conversation snapshots inside review data. The existing review Shadow DOM hosts a separate content-annotation panel.

**Tech Stack:** Python 3.9 standard library, existing vanilla JS/CSS, Ruby CDP and isolated headless macOS Chrome.

**Spec:** `docs/superpowers/specs/2026-10-28-selection-agent-comments-design.md` (approved with independent content-annotation clarification).

## Global Constraints

- Only runtime source, synthetic tests and documentation; no consumers, formal data, real jobs, global config, install, commit, push or deployment.
- `approval_policy=never`, `sandbox_mode=danger-full-access`; reuse current launcher.
- Shared, offline and disabled bridges save annotations without activating or queuing Agent work.
- Preserve evidence/timestamps; checked modifications become `changed`, never automatic `resolved`.
- Preserve old comment UI, APIs, attachment and batch behavior. New annotations never enter old batches.

## Review Focus

- Lost responses and duplicate submit must not duplicate either annotation or execution.
- Multiple annotation conversations and legacy batch tasks share one execution lock without mixing threads.
- Browser poll/navigation must preserve draft, IME, selection and historical results.
- Same quote repeated or shifted must not silently highlight unrelated text.
- Shared exports may contain public replies but no task paths, logs or executable APIs.

## Shared interfaces

Annotation base record: same evidence envelope as a comment (`id`, `number`, `text`, `status`, `page`, `anchor`, `screenshot`, `attachments`, `createdAt`, `updatedAt`), held in a separate manifest. New text anchor includes `textRange:{start,end,exact,prefix,suffix}` offsets relative to the selector container.

- GET `__review/annotations` → `{annotations:[{...record,conversation}],build,agent:{enabled,available,reason}}`.
- POST `__review/annotations` → `{annotation,agentError?}`; input `{annotation,expectedUpdate?,autoReply?:boolean,requestId?:32hex}`. New automatic sends require `requestId`; ordinary updates never auto-dispatch. Saved evidence is returned even if Agent dispatch fails.
- POST `__review/annotations/message` input `{annotationId,messageId:32hex,text}` → `{conversation}`.
- POST `__review/annotations/retry` input `{annotationId,requestId:32hex}` → `{conversation}`.
- POST `__review/annotations/stop` input `{annotationId}` → `{conversation}`.
- Public conversation: `{id,status,progress,result,error,messages:[{id,role,text,status,createdAt}],canChat}`. Status includes `queued`, `starting`, `running`, `stopping`, `completed`, `failed`, `cancelled`.
- `CodexTasks.enqueue_annotation(record, review_url, request_id)`, `.annotation_message(record, review_url, message_id, text)`, `.annotation_retry(record, review_url, request_id)`, `.annotation_stop(annotation_id)`, `.annotation_status(annotation_id)`, `.tick_annotations()`.
- `annotation_tasks.read_conversation(data_dir, annotation_id)` reads only the sanitized persisted snapshot; shared mode calls this without constructing a task manager.

### Task 1: Independent annotation UI

Files: `runtime/review.js`, `runtime/review.css` only.

- [x] Implement natural selection toolbar, preserved quote, durable Range, separate annotation entry/list/thread and composer with above API. Keep old mode handlers intact; explicitly suppress native annotation capture while old review mode is active.
- [x] Show waiting/streaming/completed/failed/stopped state, retry/stop/followup, local saved drafts, idempotent submit and refresh recovery. Keep first-message screenshot/image evidence support.
- [x] Store offline annotations separately and export self-contained annotations/replies/evidence with an offline readable artifact. No offline/shared dispatch.
- [x] Verify JS syntax and coordinate browser selectors with Task 4.

### Task 2: Persistent per-annotation Agent conversations

Files: new `runtime/annotation_tasks.py`; `runtime/codex_tasks.py`, `runtime/codex_session.py`; new `tests/test_annotation_tasks.py` and fixture extensions if needed.

- [x] Test queued A/B isolation, mutual exclusion with old batches, retry/message idempotency, old-thread resume, interrupted worker recovery and sanitized snapshots with protocol substitutes.
- [x] Implement shared interfaces, persisting queue and thread association; reuse launcher/session with independent annotation prompt. Do not inject the batch-modification Skill into annotation question turns.
- [x] New prompt judges user intent, confines modifications to consumer guidance, verifies changes before updating `__review/annotations`, and never rewrites questions as modification requests.
- [x] Run targeted task/protocol tests, then independent review.

### Task 3: Server, preservation and export integration

Files: `runtime/server.py`, `runtime/review_data.py`, `runtime/release_manager.py`, new `tests/test_annotations.py`; docs/source map and README.

- [x] Add separate manifest routes reusing established screenshot/attachment validation, Origin/project/data locks, fresh expectedUpdate and exact retry behavior. Strip any client conversation projection before persistence.
- [x] Hook server service_actions to task queue progress under data-writer ownership; preserve legacy Codex route behavior.
- [x] Add safe sanitized shared reads and blocked dispatch; include annotations and their evidence/replies in export and allowlisted package source.
- [x] Test malformed inputs, retry after lost response, stale state preservation, separate counts/batches and shared no-job behavior; run targeted server/export tests.

### Task 4: Browser integration and independent regression

Files: new `tests/test_annotations_browser.py`, `tests/browser/verify-annotations.rb`, synthetic fixtures under tests only.

- [x] Cover reading selection, cross-inline/reverse/multiline, canceled selection, composer quote and IME, resize, separate counts, screenshot/image preservation, streaming/result/failure, resend once, historical followup and refresh.
- [x] Cover shared/offline no Agent, exported reading and narrow/keyboard/focus behavior using isolated headless Chrome.
- [x] Run `PYTHONPATH=runtime python3 -m unittest discover -s tests -p 'test_*.py'` and `ruby tests/browser/verify.rb`, `ruby tests/browser/verify-attachments.rb`, `ruby tests/browser/verify-shared.rb`.
- [x] Independent final review, address findings, update validation evidence and provide local synthetic demo clearly labeled as using protocol fixture replies.

## Execution rulings

- User's approval plus latest clarification authorizes implementation; plan review does not introduce another permission gate.
- Parallel agents own disjoint files; controller owns integration. This overrides the skill's default serial implementation suggestion to satisfy active parallel delegation instructions.
- No commits: source changes remain reviewable in the user's working tree.
