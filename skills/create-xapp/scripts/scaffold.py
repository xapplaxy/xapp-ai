#!/usr/bin/env python3
"""Scaffold a new xapp from the xapplaxy/xapp-starter template.

Downloads the starter zip, extracts it into <dest>/<name>/, and rewrites the
template identifiers (package.json names, migration.yaml metadata, doc/api file
names, index.html widget id, .env key, app.css layer) to the new xapp name, and
sets up the supported languages: migration `languages`, one doc per language at
doc/<lang>/<name>.md, and <html lang> = default language. Only when more than one
language is given (a multi-language xapp) does it also add i18n: one translation file
per language at public/cdn/miniapps/<name>/locale/<lang>/i18n.json and the
src/lib/i18n.svelte.ts runtime that loads them.

On success writes <dest>/<name>/.xapp-scaffold.json (the "scaffold ready"
marker the xapp-builder subagent waits for) and prints the same JSON to stdout.

Run with:  python3 -I scaffold.py --name my-widget [--dest DIR] [--title T] [--description D]
                                  [--languages en,es,fr]   (first = default language)
"""

import argparse
import io
import json
import random
import re
import shutil
import string
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

DEFAULT_ZIP = "https://github.com/xapplaxy/xapp-starter/archive/refs/heads/main.zip"
TEMPLATE_NAME = "xapp-starter"  # identifier used in package.json / migration / doc / api
TEMPLATE_KEY = "xapp"  # runtime app key used in index.html, app.css, apps/xapp/package.json
SKILL_DIR = Path(__file__).resolve().parent.parent
I18N_RUNTIME = SKILL_DIR / "templates" / "i18n.svelte.ts"
# seed strings for the Copy/Reset controls; the builder translates the rest
CONTROLS_SEED = {"controls": {"copy": "Copy", "copied": "Copied!", "reset": "Reset"}}
NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
# BCP 47 subset: language[-Script][-REGION], e.g. en, pt-BR, zh-Hans, es-419
LANG_RE = re.compile(r"^[a-z]{2,3}(-[A-Z][a-z]{3})?(-([A-Z]{2}|[0-9]{3}))?$")


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def title_from_name(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("-"))


def parse_languages(raw: str) -> list:
    langs = []
    for part in raw.replace(" ", ",").split(","):
        code = part.strip()
        if not code:
            continue
        # normalise case: en-us -> en-US, zh-hans -> zh-Hans
        bits = code.replace("_", "-").split("-")
        norm = [bits[0].lower()]
        for b in bits[1:]:
            norm.append(b.capitalize() if len(b) == 4 else b.upper())
        code = "-".join(norm)
        if not LANG_RE.match(code):
            fail(f"'{part}' is not a valid language code (expected e.g. en, es, pt-BR, zh-Hans)")
        if code not in langs:
            langs.append(code)
    if not langs:
        fail("--languages must list at least one language code")
    return langs


def download_and_extract(url: str, target: Path) -> None:
    with urllib.request.urlopen(url, timeout=60) as resp:
        data = resp.read()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp).resolve()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for member in zf.namelist():
                dest = (tmp_path / member).resolve()
                if tmp_path not in dest.parents and dest != tmp_path:
                    fail(f"unsafe path in archive: {member}")
            zf.extractall(tmp_path)
        roots = [p for p in tmp_path.iterdir() if p.name != "__MACOSX"]
        src = roots[0] if len(roots) == 1 and roots[0].is_dir() else tmp_path
        target.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            shutil.move(str(item), str(target / item.name))


def edit(path: Path, fn) -> None:
    if not path.exists():
        print(f"WARN: {path} not found, skipped", file=sys.stderr)
        return
    text = path.read_text(encoding="utf-8")
    new = fn(text)
    if new != text:
        path.write_text(new, encoding="utf-8")


def set_json_name(path: Path, name: str) -> None:
    if not path.exists():
        print(f"WARN: {path} not found, skipped", file=sys.stderr)
        return
    raw = path.read_text(encoding="utf-8")
    indent = "\t" if re.search(r"^\t", raw, re.M) else 2
    data = json.loads(raw)
    data["name"] = name
    path.write_text(json.dumps(data, indent=indent, ensure_ascii=False) + "\n", encoding="utf-8")


def rewrite_migration(text: str, name: str, title: str, description: str, languages: list) -> str:
    path_key = "".join(random.choices(string.ascii_letters + string.digits, k=8))
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    docs = text.split("\n---")
    out = []
    for doc in docs:
        kind = re.search(r"^kind:\s*(\S+)", doc, re.M)
        kind = kind.group(1) if kind else ""
        doc = re.sub(r"^(  name:\s*).*$", rf"\g<1>{name}", doc, count=1, flags=re.M)
        if kind == "Widget":
            doc = re.sub(r"^(  title:\s*).*$", rf"\g<1>{title}", doc, count=1, flags=re.M)
            doc = re.sub(r"^(  description:\s*).*$", rf"\g<1>{description}", doc, count=1, flags=re.M)
            doc = re.sub(r"^(  pathKey:\s*).*$", rf"\g<1>{path_key}", doc, count=1, flags=re.M)
        elif kind == "Page":
            doc = re.sub(r"^(  title:\s*).*$", rf"\g<1>{title}", doc, count=1, flags=re.M)
            doc = re.sub(r"^(  description:\s*).*$", rf"\g<1>{description}", doc, count=1, flags=re.M)
            doc = re.sub(r'^(  publishedDate:\s*).*$', rf'\g<1>"{now}"', doc, count=1, flags=re.M)
            doc = re.sub(r"^(  languages:).*$", rf"\g<1> {json.dumps(languages)}", doc, count=1, flags=re.M)
            # drop the sample links block from the template
            doc = re.sub(r"^  links:\s*\n(?:    .*\n?)*", "  links: []\n", doc, count=1, flags=re.M)
            # widgets list -> just this xapp
            doc = re.sub(r"^(  widgets:)\s*\n(?:  - .*\n?)*", rf"\1\n  - {name}\n", doc, count=1, flags=re.M)
        out.append(doc)
    return "\n---".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True, help="xapp name, kebab-case (e.g. dog-age-calculator)")
    ap.add_argument("--dest", default=".", help="parent directory to create the xapp folder in (default: cwd)")
    ap.add_argument("--title", help="human title (default: derived from name)")
    ap.add_argument("--description", help="short description for migration metadata")
    ap.add_argument("--languages", default="en",
                    help="comma-separated language codes the xapp supports; first is the default (default: en). "
                         "Two or more languages turn on i18n.")
    ap.add_argument("--zip-url", default=DEFAULT_ZIP, help="starter archive URL")
    args = ap.parse_args()

    name = args.name.strip()
    if not NAME_RE.match(name):
        fail(f"'{name}' is not kebab-case (lowercase letters/digits separated by single hyphens)")
    title = (args.title or title_from_name(name)).strip()
    description = (args.description or f"{title} xapp.").strip()
    languages = parse_languages(args.languages)
    default_lang = languages[0]
    i18n = len(languages) > 1  # i18n only for multi-language xapps

    target = (Path(args.dest).expanduser() / name).resolve()
    if target.exists() and any(target.iterdir()):
        fail(f"{target} already exists and is not empty")

    download_and_extract(args.zip_url, target)

    app = target / "apps" / "xapp"
    if not app.is_dir():
        fail(f"unexpected starter layout: {app} missing")

    # package.json names
    set_json_name(target / "package.json", name)
    set_json_name(app / "package.json", name)

    # repo docs
    edit(target / "README.md", lambda t: re.sub(r"^# .*$", f"# {name}", t, count=1, flags=re.M))
    edit(target / "AGENTS.md", lambda t: t.replace(f"{TEMPLATE_NAME} is a", f"{name} is a", 1))

    # migration
    edit(app / "migration" / "migration.yaml", lambda t: rewrite_migration(t, name, title, description, languages))

    # docs: one copy of the template per language at doc/<lang>/<name>.md
    doc_dir = app / "doc"
    old_doc = doc_dir / f"{TEMPLATE_NAME}.md"
    docs = {lang: doc_dir / lang / f"{name}.md" for lang in languages}
    if old_doc.exists():
        template = old_doc.read_text(encoding="utf-8").replace("[Tool Name]", title)
        for path in docs.values():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(template, encoding="utf-8")
        old_doc.unlink()
    else:
        print(f"WARN: {old_doc} not found, per-language docs not created", file=sys.stderr)

    # api file rename
    old_api = app / "api" / f"{TEMPLATE_NAME}.py"
    new_api = app / "api" / f"{name}.py"
    if old_api.exists():
        old_api.rename(new_api)

    # i18n (multi-language only): locale JSON per language + runtime module
    i18n_files = {}
    if i18n:
        locale_dir = app / "public" / "cdn" / "miniapps" / name / "locale"
        locales = {lang: locale_dir / lang / "i18n.json" for lang in languages}
        for path in locales.values():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(CONTROLS_SEED, indent="\t", ensure_ascii=False) + "\n", encoding="utf-8")
        if not I18N_RUNTIME.exists():
            fail(f"{I18N_RUNTIME} not found, cannot set up i18n")
        i18n_ts = app / "src" / "lib" / "i18n.svelte.ts"
        i18n_ts.write_text(
            I18N_RUNTIME.read_text(encoding="utf-8").replace("__LANGUAGES__", json.dumps(languages)),
            encoding="utf-8",
        )
        i18n_files = {
            "locales": {lang: str(path) for lang, path in locales.items()},
            "i18n_ts": str(i18n_ts),
        }

    # runtime key: .env, index.html, app.css
    (app / ".env").write_text(f"VITE_XAPP_KEY={name}\n", encoding="utf-8")

    def fix_html(t: str) -> str:
        t = re.sub(r'<html lang="[^"]*"', f'<html lang="{default_lang}"', t, count=1)
        t = t.replace(f'id="wg-{TEMPLATE_KEY}"', f'id="wg-{name}"')
        t = t.replace(f'{{"{TEMPLATE_KEY}":', f'{{"{name}":', 1)
        t = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", t, count=1)
        t = re.sub(r"(<h1[^>]*>).*?(</h1>)", rf"\g<1>{title}\g<2>", t, count=1)
        return t

    edit(app / "index.html", fix_html)
    edit(
        app / "src" / "app.css",
        lambda t: re.sub(
            rf"@layer {TEMPLATE_KEY}\s*\{{\s*\.{TEMPLATE_KEY}\s*\{{",
            f"@layer {name} {{\n  .{name} {{",
            t,
            count=1,
        ),
    )

    info = {
        "status": "ready",
        "name": name,
        "title": title,
        "description": description,
        "root": str(target),
        "app_dir": str(app),
        "package_name": name,
        "languages": languages,
        "default_language": default_lang,
        "i18n": i18n,
        "files": {
            "package_json": str(app / "package.json"),
            "migration": str(app / "migration" / "migration.yaml"),
            "doc": str(docs[default_lang]),
            "docs": {lang: str(path) for lang, path in docs.items()},
            **i18n_files,
            "api": str(new_api),
            "env": str(app / ".env"),
            "index_html": str(app / "index.html"),
            "app_css": str(app / "src" / "app.css"),
            "xapp_svelte": str(app / "src" / "lib" / "XAPP.svelte"),
            "types_ts": str(app / "src" / "lib" / "types.ts"),
        },
    }
    (target / ".xapp-scaffold.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
