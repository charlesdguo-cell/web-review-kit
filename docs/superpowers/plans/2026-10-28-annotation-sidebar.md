# Annotation Sidebar Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development. User approved the design and execution. Continue without another approval gate. Do not commit or publish.

**Goal:** Simple original-text-aligned annotation cards with in-place Agent conversations and default-on per-composer response control.

**Architecture:** Rework the independent annotation surface in the existing Shadow DOM, reusing Range anchors and persistent conversations. Add an idempotent save-only reply path that never launches Agent; keep it separate from worker snapshots so streaming cannot erase saved replies.

**Tech Stack:** Existing vanilla JS/CSS, Python 3.9 standard library, Ruby CDP with isolated headless Chrome.

**Spec:** `docs/superpowers/specs/2026-10-28-annotation-sidebar-design.md` (approved by “好的 开搞”).

## Global Constraints

- `runtime/` is unique source; preserve old review mode, comments, attachments, offline/shared, optimistic timestamps, per-project job lock and request deduplication.
- No real Codex jobs, consumer upgrades/data migration, install, commit, push or deploy. All tests synthetic with isolated headless Chrome. Preserve `never` + `danger-full-access`.
- Keep existing dirty work. Backup is recorded in `artifacts/annotation-sidebar-baseline.json`; compare against that, not Git HEAD, for this increment.
- Runtime owners are disjoint. Controller owns docs/demo assets only; backend owner owns server/task/data modules; UI owner owns review.js/CSS; test owner owns browser runners/harness.
- Do not revive the rejected persistent overview + single-detail layout. Do not copy private Feishu content/images into tests or tracked documentation.

## Interfaces and decisions

- Existing GET annotations envelope remains. Extend `POST __review/annotations/message` with optional boolean `autoReply` (omission=true, existing behavior). False must be accepted by local-disabled/shared services as save-only, and never instantiate/queue/steer a launcher. Payload remains `{annotationId,messageId,text,autoReply}`; result `{conversation}`.
- A saved reply exists without an Agent job. Public conversation reports saved messages; messages with `autoReply:false` have `status:'saved'`. Persist them under review data, separate from worker-owned snapshots. Export and shared reads include them, read-only.
- Subsequent explicit autoReply=true sends include saved context without replaying saved requests. If no prior Agent job, start exactly one conversation for the current message, using original quote/comment and earlier notes as context, not as fresh executable requests. ID/body/autoReply are immutable on confirmation retries.
- Public conversation may add `initialMessageId` to distinguish the duplicated root message; do not globally dedupe equal text. UI keeps single root display and single final response per turn, and preserves legitimate repeated follow-ups.
- Browser contract: active-card legacy IDs (`annotation-input`, `annotation-followup`, `annotation-thread`, etc.) remain unique and refer only to current composer/thread. Cards use `.annotation-card[data-id]`; root `#annotation-panel`; `#annotation-agent-toggle[role=switch]`. Per-card actions carry `data-id`. Toolbar remains `[data-action=annotations]` and natural selection remains `[data-action=annotation-create]`.
- Layout: sidebar 320px at desktop, card gap 16px, active anchor prioritized with bidirectional collision avoidance. Native main-scroll carries cards; only drawer/oversized content needs own scrolling. Header fixed; navigate by document order and expose empty-viewport jump. Current-page filtering includes explicit all/resolved views.
- Accept optional script `data-annotation-root` and `data-annotation-scroll-root` selectors for explicit adapters. Auto reserve normal document body space only for safe document-scrolling layouts, preserve exact inline styles and reading anchor on close. Complex fixed/inner-scroll pages use a drawer unless explicit adapter is safe. No body transform/wrapping, no dependency/new file bundle needed.
- Offline save-only replies stored in annotations conversation, same messageId dedup semantics. Default Agent on per new composer; capability unavailable makes it disabled/effective off; frozen pending choice survives refresh.

## Review Focus

- Worker snapshot and save-only reply written concurrently must not lose/reorder messages, dispatch off messages, or leak private job paths.
- Opening/reflow/closing sidebar must restore reading position/style and keep quotes current without resize/observer feedback loops.
- Pointer clicking a text anchor must not prevent native selection/copy, page links or keyboard focus; overlapping anchors deterministic.
- Long streaming replies, card switching, IME and polling preserve per-card draft, focus and scroll.
- Initial save-only then first auto reply, failed confirmation, and shared/offline save-only all keep exact-once behavior and current message intent.

### Task 1: Sidebar UI and per-card controls

Files: `runtime/review.js`, `runtime/review.css` only.

- [x] Replace annotation list/detail views with persistent keyed cards at original-text positions, active-first collision layout, native scroll tracking, current-page count/filter/navigation, unresolved anchors accessible. Retain old review-mode handlers.
- [x] Add safe document reserve/drawer layout and restoration, including responsive changes, keyboard/touch, highlight hit-testing that preserves selection, bidirectional activation and scrolling only when needed.
- [x] Simplify cards: compact quote/author/body, one root message, one final reply, hidden low-frequency controls, one active input. Long replies expand in place; current card does not jump during polling.
- [x] Add per-composer Agent switch and wire immutable autoReply on initial/followup requests; off sends save-only across local/shared/offline. Default on only applies to new drafts, pending confirmations frozen. Stop independent; errors/queue/running shown concisely, completed only content.
- [x] Preserve evidence, export inert JSON/script escaping and offline replies; synchronize browser selector contract with Task 3. Run `node --check runtime/review.js` and coordinate synthetic browser verification, not real demo submissions.

### Task 2: Save-only replies and explicit later Agent turn

Files: `runtime/annotation_tasks.py`, `runtime/server.py`, `runtime/codex_tasks.py`, `runtime/codex_session.py`, `runtime/review_data.py` as needed; `tests/test_annotation_tasks.py`, `tests/test_annotations.py`, `tests/test_review_data.py`. No UI/browser files.

- [x] Add durable idempotent save-only message store/public projection; never overwrite worker snapshots or original annotation envelope. Validate identity/text/autoReply and preserve Origin/locking.
- [x] Extend message route while retaining omitted=true behavior, expose save-only in shared/disabled, include export/read projections. Existing initial/stop/retry contracts unchanged.
- [x] Supply saved context to a later explicit Agent turn; no prior job starts one current-message conversation; worker identity/current old jobs unchanged. Include stable root message identity.
- [x] Test no worker/jobs for off across capabilities, lost-response confirmation and changed-payload conflicts, off while running and subsequent snapshot publish, saved context on explicit later on, no stale overwrite/timestamp mutation, export/public path sanitation. Use only protocol substitute.
- [x] Run targeted `PYTHONPATH=runtime python3 -m unittest discover -s tests -p 'test_annotations.py'` and corresponding task/export suites. Report exact interfaces/UI integration requirements.

### Task 3: Sidebar browser coverage and baseline adaptation

Files: `tests/test_annotations_browser.py`, `tests/browser/verify-annotations.rb`, new `tests/test_annotation_sidebar_browser.py`, new `tests/browser/verify-annotation-sidebar.rb`, synthetic test support if needed. Do not edit runtime.

- [x] Extend harness with optional runner/synthetic document fixture; no existing user/demo content. Coordinate stable selectors with Task 1.
- [x] Adapt original 36 annotation checks for the approved new layout while retaining their actual assertions (IME, dedup, evidence/export, queue/retry, offline/shared, drift).
- [x] Add meaningful checks: distant/adjacent/overlap cards and active-first avoidance; scroll 300 moves text/card equally; no-current-viewport jump; current page/all/resolved; pointer text activation and native selection; body reserve/restore and narrow drawer; drafts/IME/focus across poll; off initial+followup and no backfill; no prior job on->one turn; lost response choice; old mode isolation.
- [x] Capture desktop/adjacent/long/narrow screenshots from fixtures. Run both annotation browser suites after runtime ready, report checks and limitations.

### Task 4: Integration, review, documentation and delivery

Owner: controller; files README, source map, new validation report, approved spec/plan, ignored demo assets.

- [x] Independently review increment diff against scoped backup, address concrete findings, run documented full unittest discovery and original review/attachment/shared browser suites.
- [x] Inspect actual fixture screenshots for minimal UI and geometry, and retained demo served assets without altering its annotations/jobs. Refresh demo runtime files; if backend restart needed, preserve data and respect existing service lifecycle, no real job mutation.
- [x] Update docs/source provenance, API/layout contracts and actual validation outcomes; mark plan/spec implemented only after verified. Retain synthetic review URL with protocol-reply limitation. No release or consumer upgrade.

## Execution rulings

- 后续缺陷修复：保留“…”菜单节点及焦点，避免 1.5 秒轮询重置原生展开状态；菜单点击与卡片激活分离，显式操作才关闭菜单，异步状态操作冻结点击时的目标状态。

- 2026-10-28 用户后续调整：移除草稿中的“放弃草稿”操作行，改为该卡片右上角 ×，复用原放弃操作及发送/待确认保护。

- User approved execution; skill handoff confirmation/commits do not apply. Parallel disjoint work follows active developer collaboration instructions over skill serial defaults.
- No new tests for cosmetic details alone; browser tests target behavior and preservation. No real model accuracy claim from protocol substitutes.
