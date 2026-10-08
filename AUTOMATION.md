# Slopforge automation

Submissions live in [GitHub Issues](https://github.com/solarfren69420/Slopforge/issues). The [activity page](https://solarfren69420.github.io/Slopforge/activity.html) links the inbox and shows upstream checks and discovery candidates. Every workflow supports manual runs from the repository's Actions tab.

## Weekly checks and discovery

The maintenance workflow runs Tuesdays at 15:23 UTC (8:23 a.m. Arizona time), and on changes to its code/configuration. GitHub schedules can run late and can be disabled by GitHub after extended inactivity in public repositories. Check the workflow history; use **Run workflow** to recover or refresh immediately.

For each catalog entry the checker records the canonical repository, archival/disabled status, default branch, latest non-prerelease release, README hash, and root LICENSE/COPYING/COPYRIGHT file hashes. Hashes detect changes; they do not interpret a license or establish feature parity. Licensing information elsewhere in the repository is outside this scan. Upstream binaries are not downloaded or executed.

`last_attempted` is the most recent attempt; `last_checked` is the most recent successful complete observation. Failed requests preserve the last good baseline and are marked `error` or `unavailable`. An unavailable repository might be private, deleted, or temporarily inaccessible; it is not automatically removed. `reviewed` remains the catalog's human review date. First successful checks establish baselines; subsequent checks compare against the previous successful observation. Change flags describe that comparison, not an outstanding-review tracker.

Edit [`data/automation-config.json`](data/automation-config.json) to add watched organizations or GitHub repository-search queries. Each search currently reads at most two pages of 30 recently updated results. Organization listings are paginated. Search result errors/incompleteness appear in the report. Candidates from overlapping sources are merged; already listed, explicitly excluded, forked, and archived repositories are skipped. Previously seen candidates remain queued even when they fall out of the bounded search results. Review the queue before adding any project; it can include infrastructure, libraries, and unrelated software.

To dismiss a candidate, add its canonical HTTPS repository URL to `excluded_repositories`. To approve one, review and add it to `data/projects.json`; the next scan removes it from the candidate queue. The report preserves every queued candidate; the public page and issue display the newest 100 by default. Queries and organizations are finite, so this reduces omissions without guaranteeing comprehensive coverage.

The report is saved as `report.json` on `automation/state`. Main catalog files are never edited by the tracker. One open bot-authored issue headed **[Automation] Weekly catalog review** is updated each run; closing it causes the next scan to open a new dashboard issue. Full reports are retained as Actions artifacts for 90 days. State publication and the dashboard update must succeed before the workflow calls the tested Pages build/deployment workflow. If a run fails, inspect its summary and logs and rerun it; the previous deployed site remains available.

The Pages build reads the current state through the GitHub API, or uses the committed initial empty report when no state exists. The public site fetches only its own generated JSON; it makes no visitor-side GitHub API calls and collects no analytics. Optional tracking-data failure does not prevent catalog browsing.

## Submission checks and drafts

The project form opens an issue after GitHub sign-in. The submission workflow runs for human-authored issue opens, edits, and reopens. It validates the GitHub URL, checks public metadata and canonical repository identity, detects existing listings, checks form selections and evidence/checkbox presence, and flags forks, archival status, and uncertain licensing. Corrections receive an acknowledgment for human review; arbitrary issues and bot-created dashboard issues are ignored.

For a new repository it prepares `project.json`, `catalog.patch`, `check.json`, and `review.md` in the `submission-N` artifact linked by its bot comment. The patch appends a draft to the catalog. **Blank fields deliberately fail catalog validation**: no platforms, license conclusions, data requirements, methodology, or human review date are invented. A duplicate gets an explanation without an addition patch. The checker updates its existing bot-authored comment when the submitter edits the form. Drafts expire after 90 days; recheck the issue through **Run workflow**, entering the issue number, to regenerate them.

Maintainer steps:

1. Open the issue, inspect upstream documentation/license and the contributor's evidence, and decide whether it belongs.
2. Download the artifact from its linked Actions run. Apply `catalog.patch` on a review branch with `git apply`, or copy the draft record into the catalog.
3. Complete every review field, check labels and data requirements, and set the actual human review date. For rewrites/custom terms, include commit-pinned evidence and license/development notes.
4. Run `python3 scripts/build.py --update-docs`, then the catalog and browser checks. Open a pull request with the issue link; merge after review and close the submission.

No submission automatically creates or merges a pull request. Prepared patches avoid requiring the separate GitHub setting that allows Actions to create PRs. No personal token is needed: maintenance has contents/issue write access, and submission checks have issue write access. Issue text is read as data, never interpolated into executable shell commands. The checker does not fetch arbitrary submitted websites or execute upstream code.

A push changing the submission checker/workflow also runs a live integration smoke test. It creates a clearly named temporary bot issue, verifies draft generation, duplicate detection, and idempotent comment updates, then closes the issue. This checks real API permissions; human issue-event delivery is provided by GitHub's configured Issues trigger.

## Browser checks

Every Pages build and pull request installs pinned Playwright and Chromium, serves `_site` locally, and exercises inventory, artwork, search/filters, favorites, persistence, detail evidence, history, keyboard shortcuts, shareable routes, six responsive widths, the activity page, and catalog loading when optional tracking fails. Failed tests block deployment. Screenshots and server logs remain available for 14 days.

## Run automation locally

The scripts use Python's standard library. Read-only runs can use public unauthenticated API access, but a full scan needs an authenticated quota. Provide an authorized token through `GH_TOKEN`; never commit it.

```sh
python3 scripts/maintenance.py collect --output test-results/local-report.json
python3 -m unittest discover -s tests -v
```

`publish` writes the state branch and the dashboard issue and requires contents/issue write permission. It is run by Actions with its ephemeral built-in token. To inspect a submission locally, pass an event JSON containing an `issue` object to `python3 scripts/submissions.py --event path/to/event.json`; omit `--publish` for read-only checking and draft generation.
