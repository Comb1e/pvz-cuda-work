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
