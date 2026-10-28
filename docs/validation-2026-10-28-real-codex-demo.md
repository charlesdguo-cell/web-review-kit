# Real Codex annotation demo validation

Date: 2026-10-28. The user explicitly authorized connecting real Codex to the demo for hands-on acceptance before publication. The [approved task](superpowers/plans/2026-10-28-real-codex-demo.md) is complete locally; publication and consumer upgrades remain pending.

## Retained experience

The real demo is **http://127.0.0.1:62891/**. Its source, generated public output, project identity, review data and jobs are separate from the original mock demo at **http://127.0.0.1:62890/**. Both services remain available. The original demo's 51 persisted data/job files were backed up outside the workspace and verified byte-identical after this trial. No mock thread ID was passed to real Codex.

This is an explicit development-source service, not a new installed release. It uses the current toolkit checkout and the authenticated local Codex CLI (`0.162.1` at validation time). The project freezes `approval_policy=never` and `sandbox_mode=danger-full-access`, required guidance, source roots, build and check commands into each dispatched request. No model override or global configuration change was made. The workflow was cross-checked against the official [Codex App Server protocol](https://learn.chatgpt.com/docs/app-server).

Only the demo's `src/index.html` is editable under its project instructions. Runtime assets are generated copies of the toolkit source. This scope is an instruction boundary, not an operating-system sandbox. No toolkit runtime changes were required during real integration. Installed releases, other consumers, unrelated jobs and release versions were not changed.

## Actual execution evidence

All three turns below used the real executable and were submitted through the content-annotation UI in independent headless Chrome profiles. They are explicitly authorized demo executions, separate from the synthetic regression suites.

| Check | Observed result |
| --- | --- |
| Doctor and live prerequisites | CLI, authentication, App Server initialization, project guidance and local service identity passed; doctor itself started no model turn. |
| New question | A natural text selection created an annotation with Agent response on by default. Real deltas and the final answer persisted; the original annotation envelope, timestamps, source, guidance, configuration and tools were unchanged. |
| Followup | A second user message resumed the same real thread, with a distinct turn ID. The reply addressed the prior answer; both final answers appeared once after a fresh navigation. No source modification occurred. |
| Explicit edit | Only the requested sentence changed, from “让每次讨论都能回到原文。” to “让每条建议都有清楚的上下文。”. Exact source comparison excluded other edits; generated HTML matched source. |
| Build | The real worker ran `python3 tools/build.py`, exit 0. |
| Static check | The real worker ran `python3 tools/check.py`, exit 0: HTML structure, anchors, review script, source/output identity and runtime/license hashes passed. |
| Browser check | The real worker ran `ruby tools/browser-check.rb`, exit 0: 1440px and 390px layouts, toolbar, required anchors, no horizontal overflow and inactive legacy review mode passed. |
| Review writeback | The worker backed up the complete data directory outside the project, reread the annotation, used fresh `updatedAt` as `expectedUpdate` with local Origin, wrote `changed` plus a result, and read it back. It did not resolve the annotation. |
| Preservation | Original annotation fields, quote/anchor, attachments, screenshot and creation time remained intact; screenshot bytes matched. The earlier question annotation stayed unchanged. |
| Final UI | Fresh desktop and narrow navigations retained two conversations, one final edit reply and the 待验收 badge. The changed quote displays 原文已变化 while preserving the quote and screenshot. Desktop uses the aligned sidebar; narrow uses the drawer. No runtime exceptions were observed. |

Real messages used `commentary` followed by `final_answer`; the UI kept the final reply once per turn. The edit's running state was also observed through the browser before completion. This sample does not establish every possible model-message phase. Failure, cancellation and retry paths retain synthetic protocol coverage; they were not exercised with the real model in this trial.

A temporary final-browser probe initially waited for an “已回复” label that this UI does not render. That probe timed out and is not counted as a pass. The corrected read-only probe checked the actual final reply, 待验收 status and retained-quote notice on both viewports and passed. A worker diagnostic comparison also accounted for the service-injected review script before confirming live HTML equivalence.

## Evidence and scope

Private runtime evidence remains in ignored `artifacts/real-codex-demo/`: submitted/completed snapshots, same-thread verification, exact source diff, command exit results, writeback/preservation checks, screenshots and final browser results. Setup evidence is in `artifacts/real-codex-demo-{doctor,service,source-before,backup}.json`. Complete backup directories remain outside the project. No real job records or screenshots were copied into tests or committed fixtures.

An independent read-only reviewer checked project isolation, frozen execution guidance, actual executable/permission configuration and question/followup preservation without dispatching tasks. The previous [menu-fix validation](validation-2026-10-28-annotation-sidebar.md#follow-up-menus-disappearing-during-synchronization) remains the toolkit regression baseline: 183 discovery tests plus the documented original review, attachment and shared browser checks. This demo-only integration did not modify that tested runtime; its new checks concern actual model execution and demo rendering, not a newly repeated full regression.

The demo remains running for the user's real-Agent acceptance. Source edits require refreshing the page to see the rebuilt content. Formal scope remains macOS and this static demo; shared/offline modes do not launch Codex. No release package, installation upgrade, deployment or production-readiness claim is part of this result.

Subsequent user feedback led to [automatic refresh and retained-location fixes](validation-2026-10-28-annotation-refresh.md). The live demo now safely refreshes newly completed edits and restores the current annotation view; rewritten quotes retain paragraph markers when their original container can be identified. That follow-up preserves all existing real data and jobs and does not dispatch another model task.
