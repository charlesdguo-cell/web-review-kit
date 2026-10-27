# Web Review Kit

Private team extraction baseline, version `0.1.0-dev`. Review any static HTML or built output with element, region and text annotations, original screenshots, image attachments, optimistic updates, offline export and shared HTTP review.

Runtime source lives only in `runtime/`. This first extraction preserves the existing service, `make_server(...)`, `CodexTasks(...)` and `run_session(...)` byte for byte. The project configuration, CLI, cross-project identity, bridge generalization and release installation are subsequent tasks. Current legacy CLI defaults and task prompts still refer to the source project's conventions; always pass explicit page and data paths during this baseline stage.

From this repository, serve an independent static site:

```sh
python3 runtime/server.py --root /absolute/path/to/site --data /absolute/path/to/reviews --port 8799
```

Open `http://127.0.0.1:8799/`. Every HTML page receives the review toolbar without application selectors or registration. Source JSX must be built by the consuming project first. Data remains outside the served output; preserve the complete data directory, including screenshots and attachments.

For HTTPS sharing behind a reverse proxy that preserves Host and path:

```sh
python3 runtime/server.py --root /absolute/path/to/site --data /absolute/path/to/reviews --bind-host 0.0.0.0 --port 8799 --base-path /team/review --public-origin https://reviews.example.test
```

Shared and offline entrypoints keep Codex disabled. The inherited local bridge uses explicit full access and `never` approval policy; this extraction verifies it with a protocol substitute only. Do not enable real tasks until project configuration and guidance are generalized in the later bridge task.

For an offline copy, place `review.js`, `review.css` and `html2canvas.min.js` together and add `<script src="review-assets/review.js" data-prototype-review></script>` in the HTML head. File entrypoints persist in browser storage and export JSON, including user attachments; original page screenshots require HTTP. Existing storage and API contracts remain intact.

Verification requires Python 3.9+, Ruby standard library and Google Chrome. Set `CHROME_BIN` if necessary; browser checks use temporary profiles and synthetic data only.

```sh
PYTHONPATH=runtime python3 -m unittest discover -s tests -p 'test_*.py'
ruby tests/browser/verify.rb
ruby tests/browser/verify-attachments.rb
ruby tests/browser/verify-shared.rb
```

The discovery command includes the Codex browser protocol fixture. To run it separately: `PYTHONPATH=runtime python3 tests/test_codex_browser.py`. Tests never launch the real Codex executable. Generated evidence goes to ignored `artifacts/`.

Migration utility: `python3 runtime/merge_review_data.py --help`. It is the inherited stopped-service importer: existing target versions win; this is not continuous synchronization. API updates require the current `updatedAt` as `expectedUpdate` and a matching Origin; technical fixes use `changed`, acceptance uses `resolved`.

See [source provenance](docs/source-map.md) and [repository rules](AGENTS.md). This round formally validates macOS only. Existing HTTPS shared review is retained and checked using isolated local browsers; Linux work and server deployment are outside this round. Packaging, remote publication, installation and end-to-end real Codex acceptance remain later work.
