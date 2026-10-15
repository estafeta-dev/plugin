# Maintenance

Canonical source: [pashbel/estafeta](https://github.com/pashbel/estafeta).
The plugin's public name is **estafeta**, its native plugin ID is `estafeta`,
and its marketplace ID is `pashbel-estafeta`.

Edit `packs/session-workflow/shared/` for the shared contract, conditional guides,
and `runtime/` implementation/schema. Each skill receives a complete copy so it
can be installed independently.

```sh
python3 scripts/workflow.py sync-contract
python3 scripts/workflow.py check
python3 scripts/test_session.py
python3 scripts/test_workflow.py
python3 scripts/test_relay.py
```

CI (`.github/workflows/ci.yml`) runs the same checks on Linux and macOS for
every push and pull request.

## Golden paths

`scripts/test_relay.py` plays the scenarios in
`scripts/golden/relay-scenarios.json`. Each scenario is a sequence of
orchestrator and worker interactions with an expected result at every step,
and the first failed step fails the scenario. Keep the set small and
representative. Add a scenario only for a new interaction pattern, and add a
failing step when you fix a delegation bug.

- **Every change and CI:** a deterministic stub worker
  (`scripts/golden/stub_worker.py`) stands in for the LLM. It also plays a
  hung worker, a garbled reply and a writer that claims checks it never ran.
- **Before a release, or when a provider, model or adapter changes:** run a
  scenario live with agent-relay against a disposable fixture. Then run
  `python3 scripts/test_relay.py --live-verify SCENARIO --root FIXTURE --map
  orch=<session> --map write-1=<delegation>`, which checks the recorded state
  read-only. Record the provider, model, date and result in VALIDATION.md.
  Live runs cost money and need the provider's login, so CI does not run them.

Change `VERSION`, every skill's metadata version, the common contract and the
three plugin manifests together. Validation rejects version drift. Provider
marketplaces point to the same `packs/session-workflow` directory. Native plugin
validation can additionally use `claude plugin validate .` and
`claude plugin validate packs/session-workflow`.

The legacy Codex-only shell installer was removed in 3.0; `workflow.py` handles
every provider, copy and link modes, explicit profile destinations and retiring
former skill names. `check` also rejects stale version strings in skill files.
Native Windows/Linux execution must be validated separately from the macOS runs.

## Naming compatibility

The source repository is `pashbel/estafeta`; the internal `packs/session-workflow`
path retains its existing name. Keep the `workflow-pack: session-workflow` ownership marker, installation
receipt and backup paths, `.agent-state/session-workflow` state directory,
handover markers and machine-ID hash prefix compatible with earlier versions.
Renaming these requires a separate migration; changing the public name does not.

## Build archives

```sh
python3 scripts/workflow.py bundle --output /path/to/estafeta-source.zip
python3 scripts/workflow.py bundle --plugin-only --output /path/to/estafeta-plugin.zip
```

The full archive contains sources, docs, catalogs and the installer. The plugin
archive contains the manifests, README, cover and six self-contained skills. Both get SHA-256
sidecars. Credentials, project runtime state and Git history are excluded.
The repository is public. Before publishing new benchmark evidence or logs,
replace local paths (for example with `$HOME` or `$OUTPUTS`) and remove personal
data. Installation never grants permission to publish or change visibility.
