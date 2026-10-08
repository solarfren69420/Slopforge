# Slopforge automation

Submissions live in [GitHub Issues](https://github.com/solarfren69420/Slopforge/issues). The [activity page](https://solarfren69420.github.io/Slopforge/activity.html) links the inbox and shows upstream checks and discovery candidates. Every workflow supports manual runs from the repository's Actions tab.

## Weekly checks and discovery

The maintenance workflow runs Tuesdays at 15:23 UTC (8:23 a.m. Arizona time), and on changes to its code/configuration. GitHub schedules can run late and can be disabled by GitHub after extended inactivity in public repositories. Check the workflow history; use **Run workflow** to recover or refresh immediately.

For each catalog entry the checker records the canonical repository, archival/disabled status, default branch, latest non-prerelease release, README hash, and root LICENSE/COPYING/COPYRIGHT file hashes. Hashes detect changes; they do not interpret a license or establish feature parity. Licensing information elsewhere in the repository is outside this scan. Upstream binaries are not downloaded or executed.

`last_attempted` is the most recent attempt; `last_checked` is the most recent successful complete observation. Failed requests preserve the last good baseline and are marked `error` or `unavailable`. An unavailable repository might be private, deleted, or temporarily inaccessible; it is not automatically removed. `reviewed` remains the catalog's human review date. First successful checks establish baselines; subsequent checks compare against the previous successful observation. Change flags describe that comparison. Repository moves remain flagged until a maintainer updates the catalog URL; archival and disabled flags also remain visible while those states apply.

Edit [`data/automation-config.json`](data/automation-config.json) to add watched organizations or GitHub repository-search queries. Each search currently reads at most two pages of 30 recently updated results. Organization listings are paginated. Search result errors/incompleteness appear in the report. Candidates from overlapping sources are merged; already listed, explicitly excluded, forked, and archived repositories are skipped. Previously seen candidates remain queued even when they fall out of the bounded search results. Review the queue before adding any project; it can include infrastructure, libraries, and unrelated software.

To dismiss a candidate, add its canonical HTTPS repository URL to `excluded_repositories`. To approve one, review and add it to `data/projects.json`; the next scan removes it from the candidate queue. The report preserves every queued candidate; the public page and issue display the newest 100 by default. Queries and organizations are finite, so this reduces omissions without guaranteeing comprehensive coverage.

The report is saved as `report.json` on `automation/state`. Main catalog files are never edited by the tracker. One open bot-authored issue headed **[Automation] Weekly catalog review** is updated each run; closing it causes the next scan to open a new dashboard issue. Full reports are retained as Actions artifacts for 90 days. State publication and the dashboard update must succeed before the workflow calls the tested Pages build/deployment workflow. If a run fails, inspect its summary and logs and rerun it; the previous deployed site remains available.

The Pages build reads the current state through the GitHub API, or uses the committed initial empty report when no state exists. The public site fetches only its own generated JSON; it makes no visitor-side GitHub API calls and collects no analytics. Optional tracking-data failure does not prevent catalog browsing.

## Submission checks and drafts

The project form opens an issue after GitHub sign-in. The submission workflow runs for human-authored issue opens, edits, and reopens. It validates the GitHub URL, checks public metadata and canonical repository identity, detects existing listings, checks form selections and evidence/checkbox presence, and flags forks, archival status, and uncertain licensing. Corrections receive an acknowledgment for human review; arbitrary issues and bot-created dashboard issues are ignored.

For each new valid repository it opens one draft PR from `submissions/issue-N`, containing `data/submissions/issue-N.json` and a readable listing table. Name, description, category, platforms, setup, source notes, and license notes are collected by the form. Repository identity and technology come from GitHub metadata; monogram/art defaults are original symbolic artwork. Existing prepared review records can supply missing fields for previously submitted projects. None of this publishes a listing or asserts a maintainer approval. A duplicate gets an explanation without an addition PR.

The checker links the PR in its existing bot comment. Edits refresh the same proposal, preserve fields a maintainer filled in the proposal, and never reopen closed PRs. Once approval is in progress, issue edits do not overwrite the approved proposal. Artifacts remain an optional backup, retained for 90 days, rather than a required publication step.

Maintainer steps:

1. Open the linked draft PR and review its listing table and upstream sources. If information is missing, ask the submitter to edit the form, or edit the proposal file through GitHub's web editor.
2. Tick **Approve and publish this reviewed listing** in the PR description. This explicitly authorizes publication of the proposed metadata.

The approval workflow runs only trusted main-branch code. It checks the approving actor's repository write permission, reads only the proposal JSON from the incoming PR, and rebuilds the PR from the current trusted main tree. It sets the human review date at approval, validates the catalog, generates the README/catalog/card art, and commits only those files plus the proposal record. Incoming PR scripts or workflows are never executed or carried into the rebuilt tree.

After catalog and browser tests pass, it verifies that approval has not been withdrawn and that the PR head and main branch have not changed during checks. It marks the draft ready, merges it, closes the linked submission, and explicitly dispatches Pages deployment (a merge using `GITHUB_TOKEN` does not trigger normal push workflows). Failed checks leave the PR unmerged, report the issue in a bot comment, and clear the checkbox so a maintainer can retry after fixing it. Repository merge policies still apply.

**One-time GitHub setting:** under repository **Settings → Actions → General → Workflow permissions**, enable **Allow GitHub Actions to create and approve pull requests**. The default token permission can remain read-only; each workflow declares its required permissions. If GitHub blocks PR creation, the bot explains this setting, preserves the prepared branch, and supplies a compare link. Enable the setting and rerun **Check project submissions** for the issue number. No personal token is required.

Submission preparation has contents/issue/PR write access. Approval additionally needs commit-status write access and Actions write access to dispatch deployment. Issue text is treated as data, never executable shell text. The checker does not fetch arbitrary submitted websites or execute upstream code. Contributors' text cannot insert an approval checkbox into the PR's structured review table.

A push changing the submission checker/workflow also runs a live integration smoke test. It creates a clearly named temporary bot issue, verifies draft generation, duplicate detection, and idempotent comment updates, then closes the issue. This checks real API permissions; human issue-event delivery is provided by GitHub's configured Issues trigger.

After that test, the workflow checks existing open human submissions and corrections, opening their proposal PRs, updating its own comments, and saving backup files in the `submission-backfill-drafts` artifact. This processes requests submitted before the checker was installed. Unrelated issues remain untouched.

## Browser checks

Every Pages build and pull request installs pinned Playwright and Chromium, serves `_site` locally, and exercises inventory, artwork, search/filters, favorites, persistence, detail evidence, history, keyboard shortcuts, shareable routes, six responsive widths, the activity page, and catalog loading when optional tracking fails. Failed tests block deployment. Screenshots and server logs remain available for 14 days.

## Run automation locally

The scripts use Python's standard library. Read-only runs can use public unauthenticated API access, but a full scan needs an authenticated quota. Provide an authorized token through `GH_TOKEN`; never commit it.

```sh
python3 scripts/maintenance.py collect --output test-results/local-report.json
python3 -m unittest discover -s tests -v
```

`publish` writes the state branch and the dashboard issue and requires contents/issue write permission. It is run by Actions with its ephemeral built-in token. To inspect a submission locally, pass an event JSON containing an `issue` object to `python3 scripts/submissions.py --event path/to/event.json`; omit `--publish` for read-only checking and draft generation.
