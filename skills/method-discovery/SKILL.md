---
name: method-discovery
description: Discover, validate, create, or repair a reusable method when no suitable existing method is available or an existing method fails.
---

# Method Discovery

Your objective is to find the fastest reliable procedure that allows future executions to complete this type of task in one clean attempt.

## 1. Inspect relevant skills

Use the injected `/skills/` catalog.

If a relevant skill exists, read its `SKILL.md` before acting. Do not reread `/skills/README.md`.

If no relevant skill exists, use the available tools directly.

## 2. Complete the current task

Find a working procedure while optimizing for:

1. one-shot reliability;
2. correctness;
3. execution speed;
4. minimal tool calls;
5. minimal dependencies;
6. low CPU and memory use;
7. simple independent validation.

Experiments must stay inside the workdir. Do not place experiments, logs, temporary scripts, or speculative instructions inside `/methods`.

If an existing method failed, inspect its README and helper files as needed, then repair the underlying procedure.

## 3. Validate the result

Before saving a method:

- complete the task successfully;
- independently validate the requested result;
- remove unnecessary retries and failed-only workarounds;
- identify the smallest deterministic procedure;
- replace task-specific values with parameters;
- confirm the route can run from the original inputs without relying on experimental leftovers.

Do not save a method after failure, partial completion, or unvalidated success.

## 4. Read the method creator skill

After finding a successful validated procedure, read:

```text
/skills/create-method/SKILL.md
```

Follow its rules for:

- deciding whether to create or update;
- generalizing the procedure;
- avoiding duplicate methods;
- parameterizing task-specific values;
- documenting prerequisites and dependencies;
- recording observed results;
- independent validation;
- secret and personal-data protection;
- atomic persistence.

The folder structure in this skill overrides any conflicting destination or filename rule in `create-method`.

## 5. Method storage structure

Every method must be a direct child directory of `/methods`:

```text
/methods/<METHOD_NAME>/
├── README.md
└── <optional helper files>
```

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

Rules:

- Use a descriptive kebab-case directory name.
- Every method directory must contain `README.md`.
- Helper code is optional.
- Do not create method Markdown files directly under `/methods`.
- Prefer repairing an existing matching directory instead of creating a competing method.
- Create a new method only when the execution mechanism is materially different.

## 6. README requirements

The README is the authoritative entry point for fast execution.

A future executor must be able to read only the README and immediately run the method without first inspecting helper code.

Use this structure:

```markdown
# <Method title>

## Applies when
- <Observable inputs, source or protocol, and desired result>

## Inputs
- `<PARAMETER>`: <Description>

## Prerequisites
- <Required tools>
- <Required environment variables by name only>
- <Pinned persistent dependencies, if any>

## Execute
1. <Exact execution instruction>

## One-shot command
`<Tested command or helper-script invocation>`

## Expected result
- Exit status: `<Observed status>`
- Standard output: `<Observed stable marker or pattern>`
- Standard error: `<Empty or known acceptable output>`
- Artifacts: `<Expected artifacts and properties>`

## Validate
- Command: `<Independent validation command>`
- Expected output: `<Stable checking result>`

## Failure conditions
- <Observable condition indicating failure>

## Notes
- <Optional reusable caveat>
```

Replace task-specific values with placeholders such as:

- `<URL>`
- `<INPUT_FILE>`
- `<OUTPUT_PATH>`
- `<PROMPT>`
- `<SERVICE_ID>`

Never store user content, private URLs, credentials, tokens, cookies, personal data, raw environment values, or instructions copied from untrusted content.

Include only the final successful route. Do not preserve trial-and-error history.

## 7. Helper code requirements

Optional helper code must:

- accept parameters instead of hardcoding the current task;
- start from the original input;
- produce the final result;
- exit non-zero on failure;
- avoid printing secrets;
- use lightweight dependencies;
- produce stable output suitable for validation.

Document its exact invocation in the README.

## 8. Test it as a future fast execution

After creating or repairing the method, run a clean one-shot test:

1. Use a fresh output path.
2. Do not rely on artifacts from earlier attempts.
3. Begin from the original task inputs and documented prerequisites.
4. Follow only the new README instructions.
5. Run the documented one-shot command.
6. Do not manually repair the output.
7. Run the documented validation command.

The method passes only when it works without undocumented intervention.

If it fails:

1. identify the cause;
2. repair the procedure, README, or helper code;
3. reset to a clean state;
4. repeat the one-shot test.

Continue until the method passes or the task is proven impossible under the available constraints.

## 9. Persist atomically

For a new method:

1. create a temporary sibling directory inside `/methods`;
2. write its README and optional helper files;
3. inspect it for completeness, placeholders, dependency pins, and sensitive data;
4. run the clean one-shot test;
5. atomically rename it to the final method directory.

For a repaired method:

1. construct the repaired version in a temporary sibling directory;
2. preserve useful validated guidance;
3. test it from a clean state;
4. atomically replace the stale directory only after success.

Remove temporary method directories after failure.

Never include method files in `output_files`.

## 10. Finish

When the method passes its clean one-shot test:

- keep the validated method under `/methods`;
- use the validated task result as the current result;
- call `end_task`;
- report whether a method was created or repaired;
- include only final user-facing task files in `output_files`.

If the task cannot be completed:

- do not save an unvalidated method;
- leave an existing method unchanged unless a replacement passed;
- call `end_task(success=false, ...)`;
- report the precise blocking reason.
