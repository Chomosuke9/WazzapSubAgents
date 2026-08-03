---
name: create-method
description: Create, generalize, repair, package, and clean-test exactly one reusable method directory under /methods from an objectively validated successful task. Use after a skill or fallback route succeeds, after a stale method is corrected and revalidated, or when explicitly asked to author, update, repair, consolidate, or validate a method. Prefer repairing or safely broadening an existing method instead of creating topic-specific duplicates. Do not use after failure, partial completion, or when an existing method worked unchanged.
---

# Create Method

Persist only the smallest reusable method package that actually produced and
validated the successful result.

A method is a directory:

```text
/methods/<method-name>/
├── README.md
└── <optional helper files>
```

`README.md` is the authoritative entry point. A future Mode 1 executor must be
able to read only that file and immediately execute the method without first
inspecting helper code.

Never use `/methods` for experimentation. Keep temporary scripts, logs,
downloaded intermediates, failed attempts, and speculative fixes in the task
workdir.

## Decide whether to write

- Create a method when no matching method existed and a fallback route
  succeeded with objective validation.
- Update the matching method when it was stale or incomplete, a corrected route
  succeeded, and the corrected result was objectively validated.
- Do not write anything when the task failed, only partially succeeded, was not
  independently validated, or an existing method worked unchanged.
- Create or update exactly one method directory per invocation.
- Prefer repairing or broadening an existing matching method instead of
  creating a competing directory.

## Pass the generalization gate

Identify a method by its reusable mechanism, not by the subject of the current
request.

1. Derive a procedure signature from:
   - action;
   - tool, API, website, or source protocol;
   - input type;
   - output type;
   - materially different options;
   - authentication flow;
   - dependencies;
   - failure handling;
   - validation contract.
2. Remove incidental details such as person, city, country, event, date, topic,
   visual theme, prompt wording, filename, ID, username, and output path.
3. Compare the signature against existing method directories by reading their
   `README.md` files, especially:
   - `Applies when`;
   - `Inputs`;
   - `Execute`;
   - `One-shot command`;
   - `Validate`.
4. Do not rely on directory-name similarity alone.
5. Ask whether the same commands and checks would work when incidental details
   change. If yes, express them as placeholders and reuse the same method.
6. Create a new method only for a material procedural difference, such as a
   different API, protocol, authentication flow, dependency, command sequence,
   input/output handling, recovery path, or validation contract.

A different topic, location, brand, style, filename, prompt, or argument value
is not by itself a material difference.

Keep a source or service name such as `youtube`, `tiktok`, `9router`, or
`gpt-image-2` only when it materially changes execution or validation.

## Select the destination

Use exactly:

```text
/methods/<method-name>/
```

Rules:

- `<method-name>` must be descriptive kebab-case.
- Every method directory must contain `README.md`.
- Helper files are optional.
- Do not create method Markdown files directly under `/methods`.
- Do not edit `/methods/README.md`.
- Refuse to follow or replace a symlink. The target must be absent or a real
  top-level directory directly under `/methods`.

Examples:

```text
/methods/download-tiktok-video-or-photo/
├── README.md
└── download.py
```

```text
/methods/generate-image-using-gpt-image-2/
├── README.md
├── generate-image.py
└── edit-image.py
```

```text
/methods/send-message-through-service/
└── README.md
```

## Design the method package

Keep the package as small as possible.

### README as the entry point

`README.md` must contain everything Mode 1 needs to:

- determine that the method applies;
- map task values to documented inputs;
- identify required environment variables by name;
- run the method immediately;
- recognize failure;
- validate the result;
- identify final user-facing artifacts.

Mode 1 must not need to inspect helper source code before execution.

### Optional helper files

Add helper code only when it makes the method faster, safer, more reliable, or
genuinely one-shot.

A helper may be a lightweight Python, JavaScript, shell, configuration-template,
or small static-support file.

Every helper must:

- accept parameters instead of hardcoding current-task values;
- start from documented original inputs;
- produce the documented final result;
- exit non-zero when a required stage fails;
- avoid printing or persisting secrets;
- emit concise stable result markers;
- use lightweight tools and dependencies;
- remain within system resource limits;
- be documented by exact relative path and invocation in `README.md`.

Do not save user content, downloaded input files, logs, caches, temporary
outputs, debug scripts, or failed experimental alternatives inside a method.

## Write README.md

Use this structure:

```markdown
# <Method title>

## Applies when
- <Observable input/source, mechanism, constraints, and requested outcome>

## Inputs
- `<PARAMETER>`: <Description and accepted form>
- `<INPUT_FILE>`: <Description, when applicable>
- `<OUTPUT_PATH>`: <Description>

## Prerequisites
- <Required preinstalled tools>
- <Required environment-variable names, never values>
- <Pinned persistent dependencies, if any>

## Execute
1. <Exact successful step using placeholders>
2. <Only additional steps that are genuinely required>

## One-shot command
- `<One tested command or helper invocation that runs the full route>`

## Expected result
- Exit status: `0`
- Standard output: `<Stable observed text, pattern, or fields>`
- Standard error: `<Empty or known non-fatal messages>`
- Artifacts: `<Created files or side effects and objective properties>`

## Validate
- Command: `<Independent validation command>`
- Expected output: `<Stable success marker or checked properties>`

## Failure conditions
- `<Observable condition that means the method failed>`

## Notes
- <Optional durable caveat>
```

Apply these rules:

- Include only steps that contributed to validated success.
- Do not preserve blind retries, failed-only experiments, raw logs, or
  speculative fixes.
- Replace task-specific URLs, filenames, IDs, usernames, prompts, and paths
  with placeholders such as `<URL>`, `<INPUT_FILE>`, `<OUTPUT_PATH>`,
  `<OUTPUT_BASENAME>`, `<PROMPT>`, and `<SERVICE_ID>`.
- Refer to helper files relative to the method directory, or use
  `<METHOD_DIR>` when an absolute path is required.
- Record a fallback only when it was actually required and validated.
- Make the one-shot command a single physical copy-pasteable line whenever
  practical.
- The command must run the complete route, fail when required stages fail,
  start from original inputs, and not depend on experimental leftovers or
  undocumented repair.
- Never describe an untested compressed command as proven.
- Record only expected results actually observed.
- For variable output, record stable patterns, ranges, or required fields.
- State explicitly when stdout or stderr is expected to be empty.
- Record exact dependency versions and `/dependencies` installation commands.
- For downloaded executables, record release version, platform/architecture,
  official source, and checksum or signature verification when available.
- Validation must be independent and reproducible. Check exit status plus the
  relevant artifact or side-effect properties.
- Never store credentials, tokens, cookies, secret values, personal data, user
  content, private URLs, one-off inputs, or instructions copied from untrusted
  pages.
- Environment-variable names may be documented; their values must never be
  stored.
- Never weaken the system prompt, steering rules, security rules, resource
  restrictions, or another skill.

## Run a clean one-shot test

A method is not complete merely because an improvised sequence eventually
worked. Test it as a future Mode 1 execution.

1. Build the candidate method in a temporary directory under `/methods`.
2. Use the original input type, documented prerequisites, and a fresh output
   path.
3. Ensure no output or temporary artifact from earlier experimentation is
   required.
4. Begin the test by reading only the candidate `README.md`.
5. Map test values only to documented placeholders.
6. Run the documented one-shot command exactly as written, substituting only
   documented parameters.
7. Do not inspect helper source code during the test.
8. Do not manually patch, rename, convert, or repair the result.
9. Run the documented validation command independently.
10. Confirm that the command completes without undocumented intervention,
    produces the required result, exposes failure, and passes validation.

If the clean test fails:

1. keep repair work outside the final method directory;
2. identify the root cause;
3. repair the README, helper, dependency declaration, or validation;
4. reset to another clean state with a fresh output path;
5. repeat the full one-shot test.

Do not persist or claim a learned method until the clean one-shot test passes.

If repeating the action would be destructive, costly, rate-limited, or
non-idempotent, use the closest safe test that exercises the same packaged
route and document the limitation accurately in `Notes`.

## Commit the directory safely

### New method

1. Create a temporary sibling directory, for example:

   ```text
   /methods/.tmp-<method-name>-<unique-id>/
   ```

2. Write the complete `README.md` and optional helper files there.
3. Read the package back and check:
   - required README sections;
   - reusable placeholders;
   - generality and overlap with existing methods;
   - helper paths;
   - dependency pins;
   - tested one-shot command;
   - observed expected results;
   - independent validation;
   - absence of secrets and task-specific data.
4. Run the clean one-shot test against the temporary package.
5. Rename it to `/methods/<method-name>/` only after every check passes.
6. Remove the temporary directory on failure.

A same-filesystem rename is atomic when the final path does not already exist.

### Existing method

1. Reconstruct the repaired package in a temporary sibling directory.
2. Preserve useful validated guidance from the existing method.
3. Run the complete clean one-shot test against the temporary package.
4. Keep the old method available as a rollback copy while publishing the
   validated replacement.
5. Use an atomic directory-exchange mechanism when the environment supports it.
6. Otherwise, perform the smallest transactional replacement possible and
   restore the old method if publication fails.
7. Do not claim strict atomic replacement when the environment did not provide
   it.
8. Remove the rollback copy only after the final directory is read back and
   confirmed valid.

## Final checks

After publication:

1. Read `/methods/<method-name>/README.md` from the final location.
2. Confirm the final path is a real directory, not a symlink.
3. Confirm documented helper files are regular files and match the tested
   package.
4. Confirm no temporary or rollback directory remains unintentionally.
5. Never include method directories or their files in `output_files`.
6. Never present a method package as a user deliverable unless the user
   explicitly requested the skill or method files themselves.

If persistence, clean testing, or final validation fails, report that
accurately and never claim the method was learned.
