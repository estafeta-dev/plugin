# Maintenance

Canonical source: [pashbel/session-workflow](https://github.com/pashbel/session-workflow).
Edit `packs/session-workflow/shared/` for the shared contract, conditional guides,
and `runtime/` implementation/schema. Each skill receives a complete copy so it
can be installed independently.

```sh
python3 scripts/workflow.py sync-contract
python3 scripts/workflow.py check
python3 scripts/test_session.py
python3 scripts/test_workflow.py
```

Change `VERSION`, every skill's metadata version, the common contract and the
three plugin manifests together. Validation rejects version drift. Provider
marketplaces point to the same `packs/session-workflow` directory. Native plugin
validation can additionally use `claude plugin validate .` and
`claude plugin validate packs/session-workflow`.

The legacy Codex-only shell installer was removed in 3.0; `workflow.py` handles
every provider, copy and link modes, explicit profile destinations and retiring
former skill names. `check` also rejects stale version strings in skill files.
Native Windows/Linux execution must be validated separately from the macOS runs.

## Build archives

```sh
python3 scripts/workflow.py bundle --output /path/to/session-workflow-source.zip
python3 scripts/workflow.py bundle --plugin-only --output /path/to/session-workflow-plugin.zip
```

The full archive contains sources, docs, catalogs and the installer. The plugin
archive contains the manifests and five self-contained skills. Both get SHA-256
sidecars. Credentials, project runtime state and Git history are excluded.
The repository is public. Before publishing new benchmark evidence or logs,
replace local paths (for example with `$HOME` or `$OUTPUTS`) and remove personal
data. Installation never grants permission to publish or change visibility.
