# Submission checklist

Work top to bottom on the day. The incognito checks matter most — they are the
only way to see what a reviewer sees, rather than what your logged-in,
cache-warmed browser shows you.

## Repository

- [ ] Repo is **public** — open it in an incognito window while signed out and
      confirm it loads
- [ ] Repo name and GitHub handle are **anonymous** — no real name, employer or
      personal handle anywhere
- [ ] `git log` shows no personal email you would rather not publish
      (`git log --format='%ae' | sort -u`)
- [ ] No AI attribution lines in any commit message or PR
      (`git log --grep='Co-Authored-By' --grep='Generated with' -i` returns nothing)
- [ ] CI badge is green on the default branch — the Actions tab shows a passing
      run for the latest commit
- [ ] Latest commit is pushed (`git status` clean, `git log origin/main..HEAD`
      empty)

## Live app

- [ ] Live URL opens in **incognito** with no login prompt
- [ ] All six tabs load with data: Dashboard, Decision Replay, Plan, Biggest
      misses, Analysis, Data quality
- [ ] Decision Replay slider and Play both work on the deployed build
- [ ] Deep link survives a **hard refresh** in incognito, e.g.
      `…/?tab=replay&day=2026-01-12&cutoff=09%3A20`
- [ ] `…/api/health` returns `{"status":"ok", "actual_rows":1488, …}`
- [ ] `…/api/docs` loads (the interactive API docs)
- [ ] Check it once on a **phone**, not just a narrow desktop window

## README

- [ ] **Live app URL is pasted in** — the placeholder
      `<PASTE VERCEL URL HERE>` is gone
- [ ] Every link works from the public repo page: `DEPLOY.md`, `FINDINGS.md`,
      `VIDEO_SCRIPT.md`, and the three `docs/*.png` images render
- [ ] Screenshots are the current UI, not an older build
- [ ] AI disclosure section is present and accurate

## Video

- [ ] Length is **under 10 minutes**
- [ ] Uploaded as **unlisted**, not private — a private video shows "Video
      unavailable" to the reviewer
- [ ] **Open the video link in incognito** and watch the first ten seconds
      through, confirming no sign-in wall
- [ ] Audio is audible throughout; no dead air at the start
- [ ] Screen text is legible at the recorded resolution — zoom the browser to
      110–125% before recording if the charts look small
- [ ] The five headline numbers are spoken correctly (see the end of
      `VIDEO_SCRIPT.md`)
- [ ] The demo uses the **live deployed app**, not localhost

## Submission form

- [ ] Repo URL
- [ ] Live app URL
- [ ] Video URL (unlisted)
- [ ] AI tools question answered: Claude Code, used to help build the project,
      reviewed, tested and directed by me
- [ ] Any "time spent" field filled in honestly
- [ ] Re-read the brief one final time and confirm every explicit requirement is
      covered: national wind only, January 2026, the live-forecast rule, the
      accuracy metrics, the historical explorer, and the signature features

## Final sweep

- [ ] Open the repo, the live app and the video in **one fresh incognito window**,
      in that order, as the reviewer will
- [ ] Nothing in the repo refers to a phase number, a TODO, or a placeholder
- [ ] Submit, then confirm you can still open all three links afterwards
