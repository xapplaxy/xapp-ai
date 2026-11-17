---
name: create-xapp
description: Create a new xapp project from the xapplaxy xapp-starter template. Downloads https://github.com/xapplaxy/xapp-starter (main.zip) and either adds the app flat at apps/<name>/ of an existing pnpm monorepo (rewriting the starter's workspace package scope to the host's) or extracts the whole starter into a folder named after the xapp, renames the template identifiers (package.json, migration/migration.yaml, doc/ and api/ file names, index.html, .env, app.css), sets the xapp's language(s), and only when the user asks for a multi-language xapp adds i18n (per-language i18n.json under public/cdn/miniapps/<name>/locale/ and the i18n.svelte.ts runtime), and in parallel runs the xapp-builder subagent to implement the xapp from an object spatial domain model JSON, or else from a reference web page or markdown spec. Use when the user asks to create, scaffold, or start a new xapp.
argument-hint: <xapp-name> [model.json | reference-url | spec.md] [--languages en,es,...] [--dest DIR] [--layout auto|standalone|monorepo] [--title "Title"] [--description "..."]
---

# Create XApp

Creates a new xapp from the xapp-starter template, then builds the xapp's functionality with
the **xapp-builder** subagent. The two run in parallel.

Two layouts (`scripts/scaffold.py --layout`, default `auto`):

| Layout | When | Result |
|---|---|---|
| `monorepo` | `dest` (or its parent, when `dest` is its `apps/`) is a pnpm workspace whose `pnpm-workspace.yaml` lists `apps/*` | only the starter's `apps/xapp` is used, placed **flat** at `<workspace>/apps/<name>/`. Starter workspace packages (`@xapputils/utils`, …) are renamed to the host's packages with the same suffix (e.g. `@onlineutils/utils`). The host's root files are left alone. |
| `standalone` | anywhere else | the whole starter repo at `<dest>/<name>/`, app in `<dest>/<name>/apps/xapp` |

`auto` picks `monorepo` whenever a workspace is detected, so running the skill inside an
existing xapps monorepo never creates a nested `apps/xapp`.

Files in this skill:
- `scripts/scaffold.py` does the download, extraction, and renames, then writes the `.xapp-scaffold.json` ready marker
- `agents/xapp-builder.md` is the builder subagent definition
- `templates/i18n.svelte.ts` is the i18n runtime the scaffold copies into `src/lib/` (multi-language xapps only)

## 1. Collect inputs

From the arguments or the conversation:

| Input | Required | Notes |
|---|---|---|
| `name` | yes | kebab-case, e.g. `dog-age-calculator`. If the user gave a phrase, convert it and confirm. |
| domain source | yes, one of | **object spatial domain model JSON** (file path or inline JSON), **or** a **reference URL**, **or** a **markdown spec** (`.md` path) |
| `languages` | no | Set this **only when the user explicitly asks for multiple languages** (e.g. "support English and German"). Use BCP 47 codes (`en`, `de`, `pt-BR`, `zh-Hans`, …), first = default, and convert names to codes ("Spanish and German" → `es,de`). Two or more languages turn on i18n. Otherwise leave it out: the xapp is single-language (`en`), and you don't ask about languages or add i18n. If the user wants one non-English language only, pass just that code (e.g. `de`). That is still single-language, with no i18n. |
| `dest` | no | default = current working directory. In a monorepo this can be the workspace root or its `apps/` |
| `layout` | no | `auto` (default), `standalone` or `monorepo`. Pass it only if the user asks |
| `title`, `description` | no | default title is derived from the name |

Priority: if a model JSON is provided, use it (the builder may still read a URL or md as
supporting context). If no model is provided, a reference URL or markdown doc is
**required**. Ask the user for one before starting and don't guess the domain.

If inline JSON is given, save it to `<scratchpad>/<name>.model.json` and pass that path.
Validate that it parses (`python3 -I -m json.tool <file>`).

Resolve `ROOT` (the folder that will hold the marker and the app files) before starting:
```bash
python3 -I <this-skill-dir>/scripts/scaffold.py --name <name> --dest <dest> [--layout ...] --dry-run
```
It prints `layout`, `root`, `workspace_root` and `exists`, and changes nothing. Use its `root` as
ROOT. If `exists` is true, stop and ask.

## 2. Run scaffold and builder in parallel

Send both of these tool calls in a **single message**:

**a) Scaffold** (Bash, foreground):
```bash
python3 -I <this-skill-dir>/scripts/scaffold.py --name <name> --dest <dest> \
  [--layout <layout>] [--title "<title>"] [--description "<description>"] [--languages <en,es,...>]
```
It prints the marker JSON (`layout`, `root`, `app_dir`, `workspace_root`, `scope_rewrites`, and
the paths of every edited file). Paths below are relative to the app folder (`app_dir`: ROOT in
monorepo mode, `ROOT/apps/xapp` in standalone mode). The script handles:
- app `package.json` → `"name": "<name>"` (standalone also renames the root `package.json`)
- **monorepo only**: starter workspace package names → host names, in every app text file
- `migration/migration.yaml` → `name`, `title`, `description`, new random `pathKey`,
  `publishedDate`, `widgets: [<name>]`, `languages: [<langs>]`, sample `links` cleared
- `doc/xapp-starter.md` → `doc/<lang>/<name>.md`, one copy per language (`[Tool Name]` → title)
- `api/xapp-starter.py` → `api/<name>.py`
- `.env` → `VITE_XAPP_KEY=<name>`
- **multi-language only** (2+ languages; the marker has `"i18n": true`):
  - `public/cdn/miniapps/<name>/locale/<lang>/i18n.json`, one per language, seeded with the
    `controls` keys
  - `src/lib/i18n.svelte.ts` from `templates/`, with `LANGUAGES` set (first = default and fallback)
- `index.html` → `<html lang="<default>">`, `id="wg-<name>"`, data key, `<title>`, `<h1>`
- `src/app.css` → `@layer <name> { .<name> { … } }`
- **standalone only**: root `README.md`, `AGENTS.md` headings

**b) Builder** (Agent, `run_in_background: true`):
- `subagent_type: "xapp-builder"` if that agent is installed. Otherwise use
  `subagent_type: "general-purpose"` and start the prompt with the full body of
  `<this-skill-dir>/agents/xapp-builder.md`.
- Prompt must include: `name`, `root` (absolute ROOT from the dry run), and the one source,
  `model: <abs path>` **or** `reference_url: <url>` **or** `spec_md: <abs path>`, plus
  `languages: <en,es,...>` **only if** the user asked for multiple languages (same list and
  order as the scaffold; first = default). Otherwise omit it. Also include
  any extra context the user gave (target audience, must-have features, category).

The builder analyses the domain while the scaffold runs and waits for
`ROOT/.xapp-scaffold.json` before editing files.

If the scaffold **fails**, stop the builder (TaskStop), report the error, and don't retry
over a partly created folder without asking.

## 3. Finish

When the builder's completion notification arrives:
1. Read its report. Spot-check (in `app_dir`) `src/lib/XAPP.svelte`,
   `migration/migration.yaml` and every `doc/<lang>/<name>.md` for leftover placeholders.
   For a multi-language xapp, also check that `XAPPContainer.svelte` calls `loadI18n` and
   that each `public/cdn/miniapps/<name>/locale/<lang>/i18n.json` is translated.
   (`grep -n "\[" doc/*/<name>.md`). Each non-default doc must be translated, not a copy.
2. Delete the marker: `rm ROOT/.xapp-scaffold.json`.
3. Tell the user:
   - where the app is (`app_dir`), and in standalone mode that the project root is `ROOT`
   - the source used and the builder's summary (inputs/outputs/API decision)
   - multi-language only: the supported languages (default first). To preview another
     language, change `<html lang>` in `<app_dir>/index.html`.
   - build/check results, including anything that failed
   - how to run it: `cd <workspace_root> && pnpm install && pnpm --filter <name> dev`
   - the builder's open questions and assumptions
