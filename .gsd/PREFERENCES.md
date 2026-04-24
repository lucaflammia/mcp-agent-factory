---
version: 1
mode: solo

# Model selection
models:
  planning: claude-sonnet-4-6
  research: claude-sonnet-4-6
  execution: claude-sonnet-4-6
  execution_simple: claude-haiku-4-5
  completion: claude-sonnet-4-6
  subagent: claude-sonnet-4-6
uat_dispatch: false
unique_milestone_ids: false

# Budget
budget_ceiling: 20
budget_enforcement: pause

# Token optimization
token_profile: budget

context_management:
  compaction_threshold_percent: 0.70 # target compaction at 70% context usage (0.5-0.95, default: 0.70)

# Dynamic model routing
dynamic_routing:
  enabled: true
  capability_routing: true          # score models by task capability (v2.59)
  tier_models:
    light: claude-haiku-4-5
    standard: claude-sonnet-4-6
    heavy: claude-opus-4-6
  escalate_on_failure: true
  budget_pressure: true
  cross_provider: true

# Terminal for AI Coding Agent
cmux:
  enabled: false
  notifications: false
  sidebar: false
  splits: false
  browser: false

# Git
git:
  auto_push: false            # push after commits
  push_branches: false        # push milestone branch
  auto_pr: false              # create PR on milestone completion
  snapshots: false
  merge_strategy: squash
  main_branch: main
  isolation: worktree
  pre_merge_check: auto       # run checks before worktree merge (true/false/"auto")
  commit_type: feat           # override conventional commit prefix
  commit_docs: true           # commit .gsd/ artifacts to git (set false to keep local)
  manage_gitignore: true      # set false to prevent GSD from modifying .gitignore
  worktree_post_create: .gsd/hooks/post-worktree-create  # script to run after worktree creation

# GSD Auto Mode Phases
phases:
  skip_research: false
  skip_reassess: false
  skip_slice_research: false
  reassess_after_slice: false

# Skills
skill_discovery: suggest
skill_staleness_days: 60     # Skills unused for N days get deprioritized (0 = disabled)
always_use_skills:
  - debug-like-expert

# Hooks
post_unit_hooks:
  - name: code-review
    after: [execute-task]
    prompt: "Review {sliceId}/{taskId} for quality and security."
    artifact: REVIEW.md
---

# GSD Skill Preferences

See `~/.gsd/agent/extensions/gsd/docs/preferences-reference.md` for full field documentation and examples.
