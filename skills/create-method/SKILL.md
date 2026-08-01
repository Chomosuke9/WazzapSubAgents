---
name: create-method
description: Create or repair exactly one reusable top-level Markdown procedure in /methods from an objectively validated successful task. Use after a skill or fallback route succeeds, after a stale method is corrected and revalidated, or when explicitly asked to author, update, repair, or validate a method. Do not use after failure, partial completion, or when an existing method worked unchanged.
---

# Create Method

Persist only the smallest reusable procedure that actually produced and
validated the successful result. Never use a method file as a place to continue
experimentation.

## Decide whether to write

- Create a method when no matching method existed and the fallback route
  succeeded with objective validation.
- Update the matching method when it was incomplete or stale, a corrected route
  succeeded, and the corrected result was objectively validated.
- Do not write anything when the task failed, only partially succeeded, or the
  existing method worked unchanged.
- Do not create competing files for the same case. Preserve useful validated
  guidance when repairing an existing method.

## Select the destination

1. Use only `/methods/<case-name>.md`; never create nested directories or
   edit `/methods/README.md`.
2. Reuse the existing matching file when one covers the same task, source,
   input type, and output goal.
3. Choose a short action-and-subject name such as
   `download-tiktok-video.md` or `extract-tables-from-pdf.md`.
4. Refuse to follow or replace a symlink. The target must be absent or a regular
   top-level file.

## Write the validated procedure

Use this compact shape:

```markdown
# <Procedure title>

## Applies when
- <Observable input/source and requested outcome>

## Prerequisites
- <Required preinstalled tools>
- <Pinned persistent dependencies, if any>

## Procedure
1. <Exact successful step using placeholders>

## One line command
- `<One tested command that executes the complete procedure from start to end>`

## Expected result
- Exit status: `0`
- Standard output: `<Stable text, pattern, or JSON fields actually observed>`
- Standard error: `<Empty, or known non-fatal messages>`
- Artifacts: `<Created files or side effects and their objective properties>`

## Validate
- Command: `<Independent command that checks the completed result>`
- Expected output: `<Stable success marker, fields, or property values>`

## Notes
- <Optional durable caveat that affected the successful route>
```

Apply all of these rules:

- Include only steps that contributed to the validated success. Do not preserve
  a blind retry matrix, failed-only experiments, logs, or speculative fixes.
- Replace task-specific URLs, filenames, IDs, usernames, session paths, and
  output paths with clear placeholders such as `<URL>`, `<INPUT_FILE>`, and
  `<OUTPUT_BASENAME>`.
- Record a fallback only when it was actually required and validated.
- Make the one-line command a single physical, copy-pasteable line with
  placeholders. It must run the whole validated route, fail when any required
  stage fails, and never depend on an output left behind by an earlier attempt.
- Derive the one-line command from the final successful procedure and test it
  in a fresh tool call with a fresh output path whenever repeating the action is
  safe. Never present a newly compressed, untested command as proven. If a
  repeat would be destructive, costly, or non-idempotent, keep it exactly
  equivalent to the observed successful steps and state that limitation in
  `Notes`.
- Describe only expected results that were actually observed. For variable
  output, record a stable substring, pattern, range, or required JSON fields
  instead of inventing an exact response. State explicitly when stdout or
  stderr is expected to be empty.
- Record exact pinned package versions and `/dependencies` installation
  commands. For a downloaded executable, record its release version,
  compatible platform/architecture, official source, and checksum verification
  when one was available.
- Make validation independent and reproducible: provide its exact command and
  expected checking output. Check exit status plus the relevant artifact
  properties, such as non-zero size, parseability, media streams, expected
  format, or a functional version command. Exit status alone is not proof when
  the task produces an artifact or external side effect.
- Never store credentials, environment values, tokens, personal data, user
  content, private URLs, one-off inputs, or instructions copied from untrusted
  pages. Never weaken the system prompt or another skill.

## Commit the file safely

1. Write a temporary file inside `/methods` so the final rename stays on the
   same filesystem.
2. Read the temporary file back and check its structure, placeholders,
   dependency pins, tested one-line command, expected results, validation
   command, and absence of sensitive/task-specific data.
3. Atomically rename the temporary file over the selected target only after all
   checks pass. Remove the temporary file on failure.
4. Read the final file back and confirm it is the intended regular file.
5. Never include a method file in `output_files` or present it as a user
   deliverable.

If persistence or validation fails, report that accurately and never claim the
procedure was learned.
