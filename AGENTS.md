# Development constraints

- Build general document capabilities over native DataProxy deliverables. DataProxy remains the source-material boundary.
- Do not add production branches, mappings, constants, prompt examples, or repair rules keyed to sample names, case IDs, document titles, particular people, dates, business fields, or expected test answers to improve individual cases.
- A sample may expose a defect. Fix it using document structure, explicit tool parameters, format semantics, or source contracts; verify the fix with structurally different fixtures as well as the triggering case.
- Business interpretation belongs to the model and task instruction. Tools validate addresses, versions, formats, source-reference existence and safe writes; reference existence is not semantic proof.
- Test incrementally: run focused capability tests during development and representative affected cases at a stage boundary. Do not run the full historical matrix after each change.
- Report deterministic tool validation, autonomous model completion, visual review and semantic review separately. Never mark a failed/externally repaired run as an autonomous first-pass success.
