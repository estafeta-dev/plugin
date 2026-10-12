Work only in this project's workspace. Implement the supplied development brief
and verify the resulting behavior. Use the existing small offline JavaScript
starter; no external dependencies, services, assets, network requests or deploy.
Preserve the documented module exports and data contracts so another developer
can integrate the project. You may add targeted tests and change the interface
design. The UI must be usable by keyboard and at a 390px viewport. Render user
input as text. Do not commit, push, modify grading tools, inspect other benchmark
workspaces, or change global agent settings. Do not delegate to other agents.

Use concise progress and a short final report: implemented behavior, checks you
actually ran and their results, limitations, and the next action. At the end of
this stage, close the development session and leave enough project-local context
for another fresh chat to continue without your conversation. Do not keep a
preview process running. You have at most 12 minutes for this stage; use the
smallest sufficient implementation and meaningful checks.

Runtime: Node and Python are available. `npm test` runs your own Node tests;
`npm run dev -- --port 4173` serves the directory. A browser check can use
Playwright from `{playwright}` with chromium.launch({channel:'chrome',headless:true})
(system Chrome is installed; bundled browsers are not). This path is a read-only dependency, not a
project output directory. The product UI and new project documents use English.
