# Project instructions

- Search relevant papers and projects when establishing solutions; record sources actually used.
- Use explicit state machines for complex transitions.
- User: Leafy.
- Use Git and Conventional Commits: `<type>(<scope>): <subject>`.
- Use feature/fix branches; never push directly to main. Use PRs and prefer squash merges.
- Rebase before merging. Remove merged feature branches.
- Put shared constants in configuration and reuse generic interfaces.
- Keep current architecture, data flow, and workflows as diagrams in `docs/architecture.md`.
- Record each version's date, previous issues, root causes, improvements, checks, and remaining issues in `docs/iteration.md`.
- Verify successful cases, known failures, and boundaries together when fixing issues.
- Check key logic with independent controls, boundary cases, and counterexamples.

## Code structure

- `src/pvz_game/engine.py` owns CPU actions, ordered simulation phases, events,
  snapshots and outcome accounting; `mechanics.py` owns shared collision geometry
  and fixed-point gait using `data/mechanics.toml`.
- `src/pvz_game/cuda/` mirrors supported default-rule simulation and public state
  in ordered CUDA batches; custom rules remain CPU-only.
- `src/pvz_game/replay.py`, `action_replay.py`, `rendering.py`, and `ui.py` provide
  verified native/research replay formats and public-state presentation.
- `tests/` covers mechanics, independent math, CPU/CUDA differential traces,
  historical compatibility and current winning replay fixtures.
