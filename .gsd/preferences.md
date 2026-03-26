---
version: 1
mode: solo
models:
  research: claude-sonnet-4-6
  planning: claude-sonnet-4-6
  execution: claude-sonnet-4-6
  completion: claude-sonnet-4-6
skill_staleness_days: 0
uat_dispatch: false
unique_milestone_ids: false
notifications:
cmux:
  enabled: false
  notifications: false
  sidebar: false
  splits: false
  browser: false
remote_questions:
git:
  main_branch: main
  isolation: worktree
phases:
  skip_research: false
  skip_reassess: false
  skip_slice_research: false
  reassess_after_slice: false
---

# GSD Skill Preferences

See `~/.gsd/agent/extensions/gsd/docs/preferences-reference.md` for full field documentation and examples.
