# Laboratory notes

- Before model execution, the evaluator launch failed because the bundled Playwright headless shell was absent. The evaluator and common runtime hint were changed to installed system Chrome. A new output directory and source hashes were frozen; no model observation was discarded. The earlier preparation/negative control remains at ../session-workflow-benchmark-2026-10-12.
- Negative control: untouched website starter scored 0/6 groups with the repaired browser. This was evaluator calibration, not a baseline model run.
- No ancestor AGENTS.md / AGENTS.override.md was found above the test workspace. The global Codex AGENTS.md is empty.
- skills/list independently confirmed zero enabled skills for all three baseline workspaces and exactly the four project-local workflow skills for all three treatment workspaces. The per-case audits retain disabled entries too.
- All coding sessions use workspace-write sandbox with network access disabled and approval policy never. Model authentication/transport still works. In the first baseline session local listen returned EPERM and Chrome exited under sandbox restrictions. Both arms retain the same permissions; external evaluation can launch Chrome. Treat those tool errors as environment limitations, not product defects.
- Independent browser evaluation uses a private local static server which it closes after scoring. Its duration is separate from coding-session wall time.
- The report renderer and outer optimized request were added after the frozen protocol. They do not change task prompts, plugin files, evaluator, execution configuration, or scoring.

- After the baseline website finished, primary W11 read Playwright cached page.url immediately after fill and observed the old URL. The UI handler updates history synchronously, and supplemental browser evaluation of document location passed 11/11. Primary results stay unchanged. grade-v2.mjs changes only W11 URL reads; an identical regrade of every saved snapshot will be used for adjudication, not extra coding/model attempts.

- Treatment uses project-local skill copies under .agents/skills, added after the common Git starter commit. They remain untracked and are included in the runtime whole-workspace checkpoint inventory. This is the frozen project-scoped installation condition, and may add bookkeeping/context overhead compared with an already-installed user-level plugin. The performance conclusions do not estimate other installation modes. All plugin files in the first treatment snapshot were verified byte-for-byte unchanged.
- In treatment website stage 2, runtime refused a plan that removed the existing phase and a transition with an outdated revision. The agent reconciled and continued; these guard refusals are orchestration events, not product defects.

- Before the first game result, audit found the generic UI1 incorrectly required form inputs in a button-only memory game. Supplemental v2 retains layout checks and validates accessible game buttons instead; website/app form checks are unchanged. Both arms and both snapshots will use this identical correction. No model prompts or products change.

- Supplemental keyboard-win check initially rejected the valid baseline victory announcement "You found all four pairs in 4 moves!" because its regex expected won/win/complete/congrat. Expanded the announcement matcher to accept that wording and reran all supplemental checks identically for both arms. Original extra-checks-v1.json and script are preserved. This did not change frozen requirement scores or any coding observation.

- After all twelve coding observations and the 62/62 frozen-source audit completed, the corrected grader was promoted to the repository for future runs and the benchmark documentation was updated. The exact measured protocol sources remain in frozen-sources/ and in the evidence archive. Plugin 2.3.0 source files are unchanged.
