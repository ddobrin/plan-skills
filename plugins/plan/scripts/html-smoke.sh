#!/usr/bin/env bash
# html-smoke.sh — smoke test for the plan swarm's html-runtime and the three html-* exemplars.
#   plugins/plan/scripts/html-smoke.sh            lint + pack everything, report
#   plugins/plan/scripts/html-smoke.sh --lint-only lint only (no files written)
# Exit 0 when every check passes. Needs node >= 18; nothing else.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN="$(cd "$HERE/.." && pwd)"
RT="$PLUGIN/assets/html-runtime"
PACK="$RT/pack.mjs"
LINT_ONLY=0; [[ "${1:-}" == "--lint-only" ]] && LINT_ONLY=1
OUT="$(mktemp -d)"; trap 'rm -rf "$OUT"' EXIT
fail=0; pass=0
ok()   { pass=$((pass+1)); printf '  ✓ %s\n' "$1"; }
bad()  { fail=$((fail+1)); printf '  ✗ %s\n' "$1"; }

echo "html-smoke · runtime at $RT"
if ! command -v node >/dev/null 2>&1; then
  echo "  ✗ node not found — html-* roles will hand over unpacked .src.html pages (that still works at file://)"; exit 1
fi
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[[ "$NODE_MAJOR" -ge 18 ]] && ok "node $(node --version)" || bad "node >= 18 required, found $(node --version)"

for f in html-runtime.js html-runtime.css pack.mjs blocks.md ORIGIN.md LICENSE; do
  [[ -s "$RT/$f" ]] && ok "present: $f" || bad "missing: $f"
done
grep -q "htmlplan" "$RT/html-runtime.js" "$RT/pack.mjs" "$RT/html-runtime.css" 2>/dev/null && bad "stale 'htmlplan' name inside runtime files" || ok "runtime fully renamed"

# 1. the runtime example packs offline
EX="$RT/examples/scheduled-send.src.html"
if node "$PACK" "$EX" --root "$PLUGIN" --role arch --quiet -o "$OUT/example.html" >"$OUT/example.log" 2>&1; then
  ok "example packs with --role arch"
  if grep -qE '<(script|link)[^>]+(src|href)="https?://' "$OUT/example.html"; then bad "example: packed page has external refs"; else ok "example: zero external refs (offline)"; fi
  grep -q 'data-html-runtime-packed' "$OUT/example.html" && ok "example: packed marker present" || bad "example: packed marker missing"
else
  bad "example failed to pack (see below)"; sed 's/^/      /' "$OUT/example.log"
fi

# 2. role lints behave: po must reject the example (it has code), recap must reject it (no Verification h2)
node "$PACK" "$EX" --role po --lint-only --quiet >/dev/null 2>&1 && bad "--role po accepted a page with doc-calls/doc-code" || ok "--role po rejects architecture blocks"
node "$PACK" "$EX" --role recap --lint-only --quiet >/dev/null 2>&1 && bad "--role recap accepted a page without Verification" || ok "--role recap requires a Verification section"

# 3. --no-ste: a page that uses an STE-unapproved word warns without the flag and not with it
cat >"$OUT/ste.src.html" <<'HTML'
<!doctype html><html lang="en"><meta charset="utf-8"><title>STE Probe</title>
<link rel="stylesheet" href="html-runtime.css"><script src="html-runtime.js" defer></script>
<body><header><h1>Probing the STE Lint</h1></header><main>
<p>We utilize this page to ensure the lint fires. However, it should not fire with the flag.</p>
<doc-note tone="info">A note.</doc-note>
</main></body></html>
HTML
cp "$RT/html-runtime.css" "$RT/html-runtime.js" "$OUT/"
n_default="$(node "$PACK" "$OUT/ste.src.html" --lint-only 2>&1 | grep -c 'ASD-STE100' || true)"
n_flag="$(node "$PACK" "$OUT/ste.src.html" --lint-only --no-ste 2>&1 | grep -c 'ASD-STE100' || true)"
[[ "$n_default" -gt 0 ]] && ok "STE lints fire by default ($n_default)" || bad "STE lints did not fire by default"
[[ "$n_flag" -eq 0 ]] && ok "--no-ste silences STE lints" || bad "--no-ste left $n_flag STE warnings"

# 4. each role's exemplar lints clean under its own role (skipped until the role exists)
declare -A ROLE=( [html-product-owner]=po [html-architect]=arch [html-implementation-recap]=recap )
for role_dir in html-product-owner html-architect html-implementation-recap; do
  exemplar="$PLUGIN/skills/$role_dir/references/exemplar.src.html"
  if [[ ! -f "$exemplar" ]]; then printf '  · %s: no exemplar yet (skipped)\n' "$role_dir"; continue; fi
  if node "$PACK" "$exemplar" --root "$PLUGIN" --role "${ROLE[$role_dir]}" --lint-only --quiet >"$OUT/$role_dir.log" 2>&1; then
    ok "$role_dir exemplar: lint clean (--role ${ROLE[$role_dir]})"
    if [[ $LINT_ONLY -eq 0 ]]; then
      if node "$PACK" "$exemplar" --root "$PLUGIN" --role "${ROLE[$role_dir]}" --quiet -o "$OUT/$role_dir.html" >/dev/null 2>&1 \
         && ! grep -qE '<(script|link)[^>]+(src|href)="https?://' "$OUT/$role_dir.html"; then ok "$role_dir exemplar: packs offline"; else bad "$role_dir exemplar: pack failed or has external refs"; fi
    fi
  else
    bad "$role_dir exemplar: lint errors"; sed 's/^/      /' "$OUT/$role_dir.log" | grep -E '✗' | head -8
  fi
  # the agents/ mirror must carry the same SKILL body (frontmatter may differ)
  if [[ -f "$PLUGIN/agents/$role_dir/agent.md" && -f "$PLUGIN/skills/$role_dir/SKILL.md" ]]; then
    a="$(awk 'f;/^---$/{c++; if(c==2)f=1}' "$PLUGIN/agents/$role_dir/agent.md" | md5sum | cut -d' ' -f1)"
    s="$(awk 'f;/^---$/{c++; if(c==2)f=1}' "$PLUGIN/skills/$role_dir/SKILL.md" | md5sum | cut -d' ' -f1)"
    [[ "$a" == "$s" ]] && ok "$role_dir: agent.md body matches SKILL.md body" || bad "$role_dir: agent.md body drifted from SKILL.md"
  fi
done

echo
if [[ $fail -eq 0 ]]; then echo "✓ html-smoke: $pass checks passed"; exit 0; else echo "✗ html-smoke: $fail failed, $pass passed"; exit 1; fi
