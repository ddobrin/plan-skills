# images/

Visual introductions to plan-swarm@3.0 for **Antigravity**. Each one targets a different audience. All of them show the same loop, from intent to release.

| Folder | Artifact | Best for | Format |
|---|---|---|---|
| `lifecycle/` | The loop: 10 stages in a ring, the typed approval phrase at each human gate, and the Path A rework arc. Three forms from one source: a fast GIF, a click-through **stepper**, and an explainer-pace **MP4** | GIF: README header, chat. Stepper: presenting and explaining. MP4: recordings, wiki | GIF (light, dark) ~37 s, 960×600, ~0.5 MB · `plan-swarm-loop-stepper.html` · MP4 (light, dark) 1:56, 1920×1200, ~2.3 MB · 960×600 PNG still (Commit stage) |
| `explainer/` | Interactive, step-by-step page: 18 steps, 4 lanes (you, the supervisor in your top-level Antigravity conversation, role subagents, control plane & git), branch graph, and files written so far | Onboarding: a new team member clicks through at their own pace | Self-contained HTML; 1280×860 PNG previews (step 13, the refused commit) |
| `cheatsheet/` | One-page poster: setup (symlink the plugin, new conversation, "swarm init"), running the swarm ("be the supervisor"), calling a role (`invoke_subagent` `TypeName`, or its skill), the loop, the six phrases, the rules, troubleshooting | Printing, pinning in a wiki, desk reference | SVG (light and dark); 3200×2080 PNG |
| `terminal-replay/` | One milestone as it looks in your top-level Antigravity conversation: the phrases you type, the supervisor's `run_command` and `invoke_subagent` calls, the hooks rewriting `$PLAN_LIB` and refusing planted phrases, early dispatches, unapproved commits, pushes, and merges, and the real git and test output. Built from the transcript of `examples/e2e_demo.py` | Showing engineers what a session looks like | GIF ~46 s, 960×600, ~1.8 MB · 960×600 PNG still (the release) |

A Claude Code edition of the same design lives in the separate plan-skills-claude repository.

## Viewing

- **GIFs, PNGs, SVGs:** open them in a browser or image viewer, or embed them in Markdown, for example `![plan-swarm loop](images/lifecycle/plan-swarm-loop-light.gif)`.
- **Loop stepper:** open `lifecycle/plan-swarm-loop-stepper.html` in a browser (offline). Each click, →, Space, or presentation-clicker press plays the next stage's animation and then waits; a press during the animation finishes it.
  - Keys: ← back, 1–9 and 0 jump to stages 1–10, Home and End go to the intro and summary, N toggles the speaker notes, T toggles the theme, F goes full screen.
  - Autoplay (off by default) advances every 4, 7 or 10 s.
  - Deep links: `#stage=4`, `#t=dark`, `#notes=0`, for example `#stage=7&t=dark`. The address bar follows along, so you can bookmark a stage.
- **Loop MP4:** about 10 s per stage, so viewers can pause and scrub. GitHub shows MP4s only as uploaded attachments, not as repository files.
- **Explainer:** open `explainer/plan-swarm-explainer.html` in a browser. It needs no network access.
  - Keys: ← and → step, and Space plays and pauses. Buttons step, jump to the first or last step, and toggle the theme.
  - Deep links: `#step=7`, `#t=dark` or `#t=light`, and `#static=1` (no animation, used for the previews). They combine, for example `#step=7&t=dark`.

## Rebuilding

The builds are standard-library Python. They need two binaries and nothing else (no pip packages):

- **Chrome or Chromium** for headless screenshots. Default `/usr/bin/google-chrome`; set `CHROME` to override, for example `CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"` on macOS.
- **ffmpeg** on `PATH` for the GIFs, MP4s, and PNG stills. Set `FFMPEG` to use another binary.

```bash
python3 images/lifecycle/build.py      # loop.html + stepper → GIFs, stills, MP4s (about 2 min)
python3 images/cheatsheet/build.py     # writes the SVGs, then renders the PNGs
```

- `lifecycle/build.py` options: `--html-only` (just `loop.html` and the stepper), `--no-mp4`, `--theme light|dark`. `cheatsheet/build.py` takes `--svg-only`.
- `_build/gifkit.py` is the shared helper. It captures each frame from a URL fragment (`#f=N&t=dark`) at 2× scale with headless Chrome (one throwaway profile per capture, six in parallel). `save_gif` feeds the frames to ffmpeg through a concat-demuxer list that carries each frame's duration, downsamples them with Lanczos, and builds **one** palette from all frames (`palettegen=stats_mode=full`) that `paletteuse` applies to every frame, so the GIF does not flicker; `diff_mode=rectangle` keeps it small. Because ffmpeg rounds concat timestamps to 1/25 s and cannot know the last frame's delay, `set_gif_delays` then writes the exact per-frame delays into the GIF's frame headers (a stdlib walk of the GIF blocks). `save_mp4` encodes the full 2× frames with the same per-frame durations (libx264, yuv420p, 30 fps). `save_png` downsamples a still.
- `lifecycle/build.py` holds the stage list, the speaker notes, and one `render(frame)` function. `loop.html` (which the GIF and MP4 screenshot) and the stepper are both generated from it, so the three forms cannot drift apart. GIF timing is in `frames()`; MP4 timing is in `VIDEO_DUR`.
- The explainer is hand-written HTML. Edit it directly; to refresh its previews, screenshot the page with `&static=1` added, in both themes, for example with `gifkit.shoot("images/explainer/plan-swarm-explainer.html", "step=13&t=dark&static=1", out, 1280, 860)` followed by `gifkit.save_png(out, preview, 1280, 860)`.
- `terminal-replay/build.py [TRANSCRIPT]` reads the e2e transcript (default `/tmp/swarm-e2e/transcript.json`; if it is missing, the build first runs `python3 examples/e2e_demo.py` from the repository root to produce it), picks a representative subset of its steps, and writes `terminal.html` (one frame per URL fragment, `#f=N`), the GIF, and the still. `--html-only` writes just the page. Every step is looked up by its label, so the build stops with a clear message if the demo changes shape. The GIF frames are captured at 1×, because every scroll repaints the whole terminal and hinted 1× text compresses about twice as well; the still is captured at 2×.

## Accuracy

Phrases, branch names (`swarm/{m}`, `swarm-wip/{m}/{task}`), stages, hook names (`PreInvocation` → `lib/approve.py`, `PreToolUse` → `lib/gate.py`), and gate messages follow `plugins/plan/README.md`, `plugins/plan/roles/supervisor.md`, `plugins/plan/topology.md`, and the scripts in `plugins/plan/lib/`. When those change, rebuild the artifacts.

- The milestone (`login-rate-limit`), the user's request and answers, dates, test counts, and tier reasons in the explainer and the loop are illustrative.
- The denial text in explainer step 13 matches the gate's message ("plan-swarm: no valid approval for this commit. Ask the user to type exactly: approve commit … g&lt;n&gt;").
- The terminal replay is condensed from `examples/e2e_demo.py`, which is not a live model run. It feeds the plugin's real hooks (`lib/approve.py`, `lib/gate.py`) the JSON events Antigravity sends and runs the real scripts, git, and tests. So the commands, the hook decisions (rewritten `$PLAN_LIB`, denials, approvals recorded), and the git and test output are copied from its transcript. The supervisor's ◆ narration and the agent-written content (intent, questions, spec, plan, code) are illustrative. `gh pr create` is allowed by the gate but not run (the demo has no gh or GitHub), so the replay shows the generated PR title and the CI ledger check instead.

## Legacy

The 2.1 animations `plan_lifecycle_light.gif` and `plan_lifecycle_dark.gif` predate the 3.0 gates, phrases, and stages; they are deleted from the working tree and are not replaced here.
