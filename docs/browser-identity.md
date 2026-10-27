# Browser project and page identity

Configured HTTP injection reads `ProjectConfig` and places one review script first in the HTML head. Existing empty `script[data-prototype-review]` tags from a static build are replaced; other resources keep their order. This is a static HTML/build-output integration, without an added late-injection or SPA lifecycle contract.

The injected attributes are `data-project-id`, `data-page-identity` and `data-browser-storage`. JSON is HTML attribute escaped. Defaults are:

```json
{
  "pageIdentity": {"strategy": "pathname", "queryKeys": [], "includeHash": false},
  "browserStorage": {"namespace": "<projectId>", "legacyKeys": []}
}
```

The supported page strategy is `pathname`. `/index.html` and `/` share identity, including beneath a deployment prefix. Only named query keys participate; keys sort lexically and repeated values retain URL order. Hash participates when `includeHash` is true. The comment's `page.path` records this identity; `page.url` always retains the full original URL, including unselected parameters and hash, as evidence. Existing stored records are not rewritten.

Configured browser copies use `prototype.review.<encodeURIComponent(namespace)>.comments` in localStorage and `.codexDrafts` / `.codexRequests` in sessionStorage. Missing or empty configured namespace falls back to projectId. Session drafts and pending-message IDs therefore share the comment project's boundary. An explicit namespace is an intentional storage identity override; keep it unique across unrelated projects.

Legacy scripts without a project ID or namespace keep their original keys. A configured project reads an old key only when its exact name is explicitly listed. The compatibility path for a Morsea consumer configuration is:

```json
{
  "browserStorage": {
    "namespace": "morsea",
    "legacyKeys": [
      "prototype.review.v1",
      "prototype.review.codexDrafts",
      "prototype.review.codexRequests"
    ]
  }
}
```

This is an opt-in example, not a migration of the existing Morsea project. Each authorized key is copied only if its destination and migration marker are absent. The original JSON string is retained unchanged, including evidence and timestamps. The corresponding storage contains a `<destination>.migrated.<encoded-original-key>` marker with source, target and copiedAt. Existing destinations are never overwritten; after a completed copy, deleting the destination does not implicitly import the legacy key again. No browser data is merged into the HTTP comment API.

Run `ruby tests/verify-projects.rb` for same-origin projects, identity, explicit migration, IME/draft retention, missing anchors, narrow screens and configured injection. Generic interaction, attachment/offline and shared checks remain in `tests/browser/`.
