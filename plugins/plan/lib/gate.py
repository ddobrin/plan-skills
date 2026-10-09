#!/usr/bin/env python3
"""PreToolUse gate and git hooks for the plan-swarm control plane (Antigravity).

Modes:
    gate.py                        Antigravity PreToolUse hook: the tool call arrives as JSON on stdin
    gate.py --git-hook             git pre-commit / pre-merge-commit hook
    gate.py --pre-push REMOTE URL  git pre-push hook (ref updates on stdin)

The gate is active in repositories that have plans/swarm.md, and stays active
(failing closed) if that file disappears after swarm-init marked the repository.

Threat model: this is a guard against well-meaning agents that try to "unblock
themselves", not against a determined adversary with shell access, who runs
with the same privileges as the hooks. Server-side branch protection, required
reviews, and the CI ledger check are the authoritative controls.

Layer 1 (this PreToolUse hook) parses run_command command lines and:
* allows `git commit` only with a matching unused approval nonce (lib/approve.py):
  `commit` for code, `intent`/`spec`/`plan` for commits that touch only plans/;
  in pr mode only on swarm/{m}; WIP commits need none, but only inside a linked
  worktree under .swarm/worktrees/ on swarm-wip/{m}/{task};
* allows pushes only as `git push <remote> swarm/{m}` from swarm/{m} itself (the
  first one needs `approve pr`) and `git push <remote> <tag>` after `approve
  release`; never the default branch, worktree branches, deletes, or force;
* refuses history rewrites, hook bypasses, git aliases and config tricks,
  unknown git subcommands, git hidden inside other commands, and `gh` merges,
  releases, and write API calls;
* refuses agent access to the git directory and writes (run_command,
  write_to_file, replace_file_content, multi_replace_file_content, notebook_edit)
  to plans/swarm.md (and its parents), approvals.md, the plugin, and Antigravity's
  hook and plugin configuration;
* refuses dispatching an `engineer` (invoke_subagent or run_workflow) before the
  milestone's `plan` approval;
* refuses planting an approval phrase as somebody else's input: `send_message`
  calls and dispatches whose whole message is one.

It also captures approval phrases (lib/approve.capture) before checking, and
expands $PLAN_LIB in command lines to this plugin's lib directory.

Layer 2 (git hooks) re-checks commits with a one-time ticket from layer 1 and
checks every pushed commit on swarm/{m} against the approvals ledger.

Output: nothing for a neutral answer; {"decision": "deny", "reason": ...} to
block; {"decision": "allow", "overwrite": {...}} only to expand $PLAN_LIB (allow
is a no-op in Antigravity, so the user's own permission settings still apply). Any
internal error in a plan-swarm repository is a deny (fail closed).
"""
import fnmatch
import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import antigravity  # noqa: E402
import swarmdoc  # noqa: E402
import swarmgit as sg  # noqa: E402

KNOWN_SUBCOMMANDS = {
    "add", "annotate", "apply", "archive", "bisect", "blame", "branch", "bundle", "cat-file",
    "check-attr", "check-ignore", "checkout", "cherry", "cherry-pick", "clean", "commit", "config",
    "count-objects", "describe", "diff", "diff-files", "diff-index", "diff-tree", "difftool", "fetch",
    "for-each-ref", "format-patch", "fsck", "gc", "grep", "hash-object", "help", "init", "log",
    "ls-files", "ls-remote", "ls-tree", "maintenance", "merge", "merge-base", "merge-file",
    "merge-tree", "mv", "name-rev", "notes", "pull", "push", "range-diff", "rebase", "reflog",
    "remote", "repack", "reset", "restore", "rev-list", "rev-parse", "revert", "rm", "shortlog", "show",
    "clone", "prune", "interpret-trailers", "check-ref-format", "request-pull", "citool", "gui",
    "show-branch", "show-ref", "sparse-checkout", "stage", "stash", "status", "submodule", "switch",
    "symbolic-ref", "tag", "update-index", "var", "verify-commit", "verify-tag", "version",
    "whatchanged", "worktree", "write-tree", "lfs",
} | {"update-ref", "commit-tree", "filter-branch", "filter-repo", "replace", "am", "fast-import",
     "send-pack", "http-push", "receive-pack"}
HISTORY_PLUMBING = {"update-ref", "commit-tree", "filter-branch", "filter-repo", "replace", "am",
                    "fast-import", "send-pack", "http-push", "receive-pack"}
# Long options that must never be used, per subcommand; git accepts any unique prefix.
DANGER = {
    "commit": ("--no-verify", "--amend", "--pathspec-from-file"),
    "push": ("--force", "--force-with-lease", "--force-if-includes", "--delete", "--mirror",
             "--prune", "--all", "--tags", "--follow-tags", "--no-verify"),
    "tag": ("--delete", "--force"),
    "merge": ("--no-squash", "--commit", "--ff", "--no-ff", "--ff-only", "--continue"),
    "checkout": ("--force",), "switch": ("--force-create", "--force"),
}
SHORT_DANGER = {"commit": "n", "push": "fd", "tag": "fd"}
VALUE_SHORT = {"commit": "mFCct", "tag": "mFu", "push": "o", "merge": "msX", "checkout": "bB",
               "switch": "cC", "cherry-pick": "mX", "revert": "mX", "branch": "", "reset": "",
               "pull": "sX", "rm": "", "mv": "", "restore": "s", "fetch": "o", "config": ""}
VALUE_LONG = {"--message", "--file", "--author", "--date", "--template", "--reuse-message",
              "--reedit-message", "--cleanup", "--trailer", "--local-user", "--push-option", "--repo",
              "--receive-pack", "--exec", "--strategy", "--strategy-option", "--source", "--orphan",
              "--upload-pack", "--depth"}
VALUE_LONG_BY_SUB = {"commit": {"--fixup", "--squash"}}
GIT_ENV_DENY = re.compile(r"^GIT_(DIR|WORK_TREE|INDEX_FILE|COMMON_DIR|OBJECT_DIRECTORY|"
                          r"ALTERNATE_OBJECT_DIRECTORIES|EXEC_PATH|NAMESPACE|CEILING_DIRECTORIES|"
                          r"CONFIG\w*)=")
CONFIG_DENY = ("alias.", "include", "core.hookspath", "remote.", "push.", "branch.", "url.",
               "core.worktree", "core.sshcommand", "core.bare", "receive.", "transfer.")
GATED_WORDS = re.compile(r"\b(commit|push|tag|merge|rebase|reset|pull|am|cherry-pick|revert|update-ref|"
                         r"commit-tree|send-pack|fetch|checkout|switch|branch|config|filter-branch|"
                         r"fast-import|worktree|remote)\b|--no-verify")
WRITERS = {"tee", "rm", "mv", "cp", "truncate", "dd", "install", "ln", "chmod", "chown", "touch",
           "unlink", "shred", "rsync", "rmdir"}
GIT_WRAPPERS = {"timeout", "nohup", "stdbuf", "caffeinate", "nice", "time", "env", "sudo", "command", "exec",
                "ionice", "chrt", "taskset", "doas", "xargs"}
INTERPRETERS = {"python", "python3", "node", "ruby", "perl", "bash", "sh", "zsh", "osascript", "deno", "bun"}
FORBIDDEN_WORDS = ("approve.py", "swarmgit", "plan-swarm", "PLAN_SWARM")
INTERPRETER_WORDS = ("approvals.md", "swarm.md") + FORBIDDEN_WORDS
REDIRECT = re.compile(r"(?<![<>&0-9])[0-9&]?>{1,2}\|?\s*(['\"]?)([^\s;&|'\"<>]+)\1")
GIT_DIR_MENTION = re.compile(r"(^|[\s/'\"=(])\.git($|[\s/'\")])")
WRAPPERS = {"command", "exec", "env", "sudo", "nice", "time", "timeout", "nohup", "stdbuf", "caffeinate",
            "xargs", "ionice", "chrt", "taskset", "doas", "eval", "!", "{", "if", "then", "else", "do",
            "while", "until"}


class Deny(Exception):
    pass


# --------------------------------------------------------------------------
# command parsing

def unquoted_newlines_to_semicolons(command):
    """Treat unquoted newlines as command separators; join backslash continuations."""
    out, quote, i = [], None, 0
    while i < len(command):
        ch = command[i]
        if ch == "\\" and quote != "'" and i + 1 < len(command):
            out.append(" " if command[i + 1] == "\n" else command[i:i + 2])
            i += 2
            continue
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "\n":
            ch = " ; "
        out.append(ch)
        i += 1
    return "".join(out)


def simple_commands(command):
    """Split a shell command into simple commands (token lists), respecting quotes."""
    lexer = shlex.shlex(unquoted_newlines_to_semicolons(command), posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    current, out = [], []
    for tok in lexer:
        if tok and set(tok) <= set(";&|()"):
            if current:
                out.append(current)
            current = []
        else:
            current.append(tok)
    if current:
        out.append(current)
    return out


def split_env(cmd):
    env = []
    while cmd and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", cmd[0]):
        env.append(cmd[0])
        cmd = cmd[1:]
    return env, cmd


def parse_git(cmd):
    """(subcommand, args, global_opts) for a token list starting with git, else None."""
    if not cmd or os.path.basename(cmd[0]) != "git":
        return None
    i, opts = 1, []
    while i < len(cmd) and cmd[i].startswith("-"):
        opt = cmd[i]
        opts.append(opt)
        if opt in ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
                   "--config-env", "--super-prefix") and i + 1 < len(cmd):
            opts.append(cmd[i + 1])
            i += 1
        i += 1
    return (cmd[i], cmd[i + 1:], opts) if i < len(cmd) else ("", [], opts)


def long_name(tok):
    return tok.split("=", 1)[0]


def matches_long(tok, options):
    """True if tok is one of options or a unique-looking prefix of one (git accepts prefixes)."""
    if not tok.startswith("--") or tok == "--":
        return False
    name = long_name(tok)
    return any(name == o or (len(name) >= 4 and o.startswith(name)) for o in options)


def scan(sub, args):
    """Split args into (flags, positionals, pathspecs) honouring value options and `--`."""
    vshort = VALUE_SHORT.get(sub, "")
    flags, pos, specs, skip, after = [], [], [], False, False
    for a in args:
        if skip:
            skip = False
            continue
        if after:
            specs.append(a)
        elif a == "--":
            after = True
        elif a.startswith("--"):
            flags.append(a)
            if "=" not in a and (long_name(a) in VALUE_LONG or long_name(a) in VALUE_LONG_BY_SUB.get(sub, ())):
                skip = True
        elif a.startswith("-") and len(a) > 1:
            flags.append(a)
            letters = a[1:]
            for idx, ch in enumerate(letters):
                if ch in vshort:
                    skip = idx == len(letters) - 1  # value is the next token unless attached
                    break
        else:
            pos.append(a)
    return flags, pos, specs


def short_cluster(flags, letter):
    return any(f.startswith("-") and not f.startswith("--") and letter in f[1:] for f in flags)


# --------------------------------------------------------------------------
# paths

def _norm(path):
    p = os.path.realpath(path)
    return p.casefold() if sys.platform == "darwin" else p


def _inside(path, base):
    return bool(base) and (path == base or path.startswith(base.rstrip(os.sep) + os.sep))


class Context:
    def __init__(self, root, cfg, store, invalid=None):
        self.root, self.cfg, self.store, self.invalid = root, cfg, store, invalid
        self.head = sg.head(root)
        self.branch = sg.branch(root)
        self.moniker, self.task = sg.swarm_branch(self.branch)
        self.mode = cfg["delivery"]["mode"]
        self.gitdir = _norm(sg.common_dir(root)) if sg.common_dir(root) else ""
        main_root = os.path.dirname(sg.common_dir(root)) if sg.common_dir(root) else root
        self.main_root = main_root
        self.linked_wip = bool(self.task) and sg.is_linked_worktree(root) and _inside(
            _norm(root), _norm(os.path.join(main_root, ".swarm", "worktrees", self.moniker)))
        swarm_md = _norm(os.path.join(main_root, "plans", "swarm.md"))
        self.swarm_md = swarm_md
        self.swarm_ancestors = {_norm(main_root), _norm(os.path.join(main_root, "plans")), swarm_md,
                                _norm(root), _norm(os.path.join(root, "plans")),
                                _norm(os.path.join(root, "plans", "swarm.md"))}
        plugin = antigravity.PLUGIN_ROOT
        self.protected_prefixes = [_norm(plugin)]
        home = os.path.expanduser("~")
        gemini = os.path.join(home, ".gemini")
        self.protected_files = {_norm(os.path.join(gemini, "config", n))
                                for n in ("hooks.json", "config.json", "plugins.json", "agents.json",
                                          "skills.json", "mcp_config.json")}
        self.protected_files |= {_norm(os.path.join(gemini, n)) for n in ("settings.json", "trustedFolders.json")}
        self.protected_files |= {_norm(os.path.join(r, d, n)) for r in (root, main_root)
                                 for d in (".agents", "_agents", ".gemini")
                                 for n in ("hooks.json", "plugins.json", "settings.json")}
        installed = os.path.join(gemini, "config", "plugins", "plan")
        if os.path.exists(installed):
            self.protected_prefixes.append(_norm(installed))
        self.actions = []  # run only if the whole command is allowed

    def hint(self, kinds):
        m = self.moniker or "<milestone>"
        hints = {"commit": f"approve commit {m} g<n>", "pr": f"approve pr {m}",
                 "release": "approve release <version>", "plan": f"approve plan {m}",
                 "spec": f"approve spec {m}", "intent": f"approve intent <slug> as {m}"}
        return " / ".join(hints[k] for k in kinds)

    def protected_write(self, token, cwd):
        """Reason string if writing token (a path) would touch a protected location."""
        p = _norm(os.path.join(cwd, os.path.expanduser(token)))
        if _inside(p, self.gitdir):
            return "the git directory belongs to git and the plan-swarm control plane"
        if p in self.swarm_ancestors:
            return "plans/swarm.md (and the folders that hold it) are changed by people, not agents"
        if os.path.basename(p) == "approvals.md":
            return "approvals.md is written only by the approval hook"
        if p in self.protected_files or any(_inside(p, b) for b in self.protected_prefixes):
            return "the plan plugin and Antigravity's hook, plugin, and settings files are not edited by agents"
        return None


# --------------------------------------------------------------------------
# layer 1 checks

def check_commit(ctx, args, staged_by_command):
    flags, pos, specs = scan("commit", args)
    if any(matches_long(f, DANGER["commit"]) for f in flags) or short_cluster(flags, "n"):
        raise Deny("commits must not skip hooks, amend, or read pathspecs from a file")
    if ctx.invalid:
        raise Deny(f"plans/swarm.md is invalid ({ctx.invalid}); commits are refused until it is fixed")
    specs = specs + pos
    if specs:
        changed = sg.changed_paths(ctx.root, include_unstaged=True)
        paths = {p for p in changed for s in specs
                 if p == s.rstrip("/") or p.startswith(s.rstrip("/") + "/") or fnmatch.fnmatch(p, s)}
    else:
        include_all = staged_by_command or short_cluster(flags, "a") or any(matches_long(f, ("--all",)) for f in flags)
        paths = sg.changed_paths(ctx.root, include_unstaged=include_all)

    if ctx.task and ctx.linked_wip:  # engineer WIP inside its own worktree
        if any(os.path.basename(p) == "approvals.md" for p in paths):
            raise Deny("WIP commits must not include approvals.md")
        return

    ledger_rel = f"plans/active_milestones/{ctx.moniker}/approvals.md" if ctx.moniker else None
    if ledger_rel and paths == {ledger_rel}:
        prs = [r for r in sg.valid_nonces(ctx.store, ctx.head, ["pr"]) if r.get("moniker") == ctx.moniker]
        if prs:  # record the PR approval itself; the nonce stays for the push
            ctx.actions.append(lambda rec=prs[0]: sg.write_ticket(ctx.store, ctx.head, rec, True))
            return

    plans_only = bool(paths) and all(p.startswith("plans/") for p in paths)
    kinds = ["commit"] + (["intent", "spec", "plan"] if plans_only else [])
    for rec in sg.valid_nonces(ctx.store, ctx.head, kinds):
        m = rec.get("moniker")
        if ctx.mode == "pr" and ctx.branch != f"swarm/{m}":
            continue
        if rec["kind"] != "commit" and not any(p.startswith(f"plans/active_milestones/{m}/") for p in paths):
            continue
        ctx.actions.append(lambda rec=rec, po=(rec["kind"] != "commit"): (
            sg.consume(rec), sg.write_ticket(ctx.store, ctx.head, rec, po)))
        return
    why = sg.stale_reason(ctx.store, ctx.head, kinds)
    where = " on branch swarm/<milestone>" if ctx.mode == "pr" and not ctx.moniker else ""
    raise Deny(f"no valid approval for this commit{where}" + (f" ({why})" if why else "")
               + f". Ask the user to type exactly: {ctx.hint(kinds if plans_only else ['commit'])}")


def check_push(ctx, args, opts):
    if any(o == "-c" or o.startswith("-c") for o in opts):
        raise Deny("pushes may not override git configuration with -c")
    flags, pos, _ = scan("push", args)
    if any(matches_long(f, ("--tags", "--follow-tags")) for f in flags):
        raise Deny("push a release tag explicitly: git push origin <version>")
    if any(matches_long(f, DANGER["push"]) for f in flags) or short_cluster(flags, "f") or short_cluster(flags, "d"):
        raise Deny("force, delete, mirror, prune, and all-branch pushes are not allowed")
    if ctx.invalid:
        raise Deny(f"plans/swarm.md is invalid ({ctx.invalid}); pushes are refused until it is fixed")
    if len(pos) < 2:
        raise Deny("name the remote and the ref explicitly, for example: git push origin swarm/<milestone>")
    for ref in pos[1:]:
        if ref.startswith("+"):
            raise Deny("force refspecs (+ref) are not allowed")
        src, dst = ref.split(":", 1) if ":" in ref else (ref, ref)
        if src == "":
            raise Deny("deleting remote refs is not allowed")
        if src == "HEAD":
            src = ctx.branch
        if dst == "HEAD":
            dst = ctx.branch
        src_n = src.replace("refs/heads/", "").replace("refs/tags/", "")
        dst_n = dst.replace("refs/heads/", "").replace("refs/tags/", "")
        is_tag = dst.startswith("refs/tags/") or (not dst.startswith("refs/heads/")
                                                  and bool(sg.git("tag", "--list", dst_n, cwd=ctx.root)))
        if is_tag:
            if src_n != dst_n or not sg.allowance(ctx.store, f"push-tag-{dst_n}"):
                raise Deny(f"pushing tag {dst_n} needs a fresh release approval: approve release {dst_n}")
            continue
        if sg.is_default_branch(dst_n, ctx.root):
            raise Deny(f"the swarm never pushes {dst_n}; merges happen in the pull request")
        m, task = sg.swarm_branch(dst_n)
        if task:
            raise Deny("worktree branches (swarm-wip/*) are never pushed")
        if not m:
            raise Deny(f"plan-swarm only pushes swarm/<milestone> branches; {dst_n} is pushed by people")
        if src_n != dst_n:
            raise Deny(f"push swarm/{m} from itself (git push origin swarm/{m}), not from {src_n}")
        if sg.git("rev-parse", "--verify", "--quiet", f"refs/remotes/{pos[0]}/{dst_n}", cwd=ctx.root):
            continue  # updating an open PR; the pre-push hook checks every new commit
        recs = [r for r in sg.valid_nonces(ctx.store, ctx.head, ["pr"]) if r.get("moniker") == m]
        if not recs and ledger_only_commit(ctx.root, m, ctx.head):
            parent = sg.git("rev-parse", "--verify", "--quiet", f"{ctx.head}^", cwd=ctx.root)
            recs = [r for r in sg.valid_nonces(ctx.store, parent, ["pr"]) if r.get("moniker") == m]
        if not recs:
            why = sg.stale_reason(ctx.store, ctx.head, ["pr"])
            raise Deny("opening the PR needs approval" + (f" ({why})" if why else "")
                       + f". Ask the user to type exactly: approve pr {m}")
        ctx.actions.append(lambda rec=recs[0]: sg.consume(rec))


def ledger_only_commit(root, moniker, sha):
    """True if commit sha changes exactly the milestone's approvals.md."""
    changed = sg.git("diff-tree", "--no-commit-id", "--name-only", "-r", sha, cwd=root).split()
    return changed == [f"plans/active_milestones/{moniker}/approvals.md"]


def check_tag(ctx, args):
    listing = {"-l", "--list", "--contains", "--no-contains", "--points-at", "--merged", "--no-merged", "-n",
               "--sort", "--format", "--column", "--no-column"}
    flags, pos, _ = scan("tag", args)
    if any(matches_long(f, DANGER["tag"]) for f in flags) or short_cluster(flags, "f") or short_cluster(flags, "d"):
        raise Deny("deleting or moving tags is not allowed")
    if not pos or any(long_name(f) in listing for f in flags):
        return
    if ctx.invalid:
        raise Deny(f"plans/swarm.md is invalid ({ctx.invalid}); tags are refused until it is fixed")
    version = pos[0]
    if len(pos) > 1 and sg.git("rev-parse", "--verify", "--quiet", pos[1] + "^{commit}", cwd=ctx.root) != ctx.head:
        raise Deny("release tags are created on the current HEAD only")
    for rec in sg.valid_nonces(ctx.store, ctx.head, ["release"]):
        if (rec.get("version") or "").lstrip("v") == version.lstrip("v"):
            ttl = ctx.cfg["approvals"]["nonce_ttl_minutes"] * 60
            ctx.actions.append(lambda rec=rec: (sg.consume(rec), sg.allowance(ctx.store, f"push-tag-{version}", ttl)))
            return
    why = sg.stale_reason(ctx.store, ctx.head, ["release"])
    raise Deny(f"creating tag {version} needs approval" + (f" ({why})" if why else "")
               + f". Ask the user to type exactly: approve release {version}")


def resolves_to_head(ctx, rev):
    return sg.git("rev-parse", "--verify", "--quiet", rev + "^{commit}", cwd=ctx.root) == ctx.head


def check_git(ctx, sub, args, opts, env, cwd, staged_by_command):
    for e in env:
        if GIT_ENV_DENY.match(e):
            raise Deny(f"{e.split('=')[0]} changes which repository or configuration git uses; not allowed")
    i = 0
    while i < len(opts):
        o = opts[i]
        value = opts[i + 1] if o in ("-c", "--config-env") and i + 1 < len(opts) else (
            o[2:] if o.startswith("-c") and len(o) > 2 else (o.split("=", 1)[1] if "=" in o else ""))
        if o.startswith("--config-env") or o.startswith("--exec-path"):
            raise Deny("git --config-env / --exec-path are not allowed in a plan-swarm repository")
        if (o == "-c" or (o.startswith("-c") and not o.startswith("--"))) and value.lower().startswith(CONFIG_DENY):
            raise Deny("this git -c setting (aliases, hooks, remotes, includes) is not allowed")
        i += 2 if o in ("-c", "-C", "--git-dir", "--work-tree", "--namespace", "--config-env") else 1
    if not sub:
        return
    if sub not in KNOWN_SUBCOMMANDS:
        raise Deny(f"`git {sub}` is not a known git command (aliases are not allowed in a plan-swarm repository)")
    redirect = any(o in ("-C", "--git-dir", "--work-tree", "--namespace", "--bare") or o.startswith(("--git-dir=", "--work-tree=", "-C"))
                   for o in opts if not o.startswith("-c"))
    if redirect and sub not in ("status", "log", "diff", "show", "rev-parse", "ls-files"):
        raise Deny(f"run `git {sub}` from inside the repository, without -C / --git-dir / --work-tree")
    if sub in HISTORY_PLUMBING:
        raise Deny(f"`git {sub}` writes history or refs directly and is not allowed in a plan-swarm repository")
    on_swarm = bool(ctx.moniker) and not ctx.task
    flags, pos, specs = scan(sub, args)

    if sub == "commit":
        check_commit(ctx, args, staged_by_command)
    elif sub == "push":
        check_push(ctx, args, opts)
    elif sub == "tag":
        check_tag(ctx, args)
    elif sub == "merge":
        if any(matches_long(f, DANGER["merge"]) for f in flags):
            raise Deny("only `git merge --squash` (no commit) or `--abort` is allowed")
        if not any(long_name(f) in ("--squash", "--abort") for f in flags):
            raise Deny("only `git merge --squash` (no commit) is allowed; commits go through the commit gate")
    elif sub == "pull":
        if on_swarm or not any(long_name(f) == "--ff-only" for f in flags):
            raise Deny("use `git pull --ff-only` on the default branch only")
    elif sub in ("cherry-pick", "revert"):
        if not (short_cluster(flags, "n") or any(long_name(f) in ("--no-commit", "--abort", "--quit") for f in flags)):
            raise Deny(f"`git {sub}` must use --no-commit; commits go through the commit gate")
    elif sub == "rebase":
        if not any(long_name(f) in ("--abort", "--quit") for f in flags):
            raise Deny("rebasing rewrites history and is not allowed in a plan-swarm repository")
    elif sub == "reset" and on_swarm:
        if any(long_name(f) in ("--soft", "--keep") for f in flags):
            raise Deny("resetting a swarm branch rewrites approved history")
        for p in pos:
            if sg.git("rev-parse", "--verify", "--quiet", p + "^{commit}", cwd=ctx.root) and not resolves_to_head(ctx, p):
                raise Deny("resetting a swarm branch to another commit rewrites approved history")
    elif sub == "branch":
        writing = [f for f in flags if long_name(f) in ("--delete", "--move", "--copy", "--force", "--set-upstream-to")
                   or (f.startswith("-") and not f.startswith("--") and set(f[1:]) & set("dDmMcCfu"))]
        names = [p for p in pos if sg.swarm_branch(p)[0] and not sg.swarm_branch(p)[1]]
        if names and (writing or len(pos) > 1):
            raise Deny(f"{names[0]} is a milestone's evidence; it is not deleted, moved, copied, forced, or re-pointed")
    elif sub in ("checkout", "switch"):
        if any(matches_long(f, DANGER[sub]) for f in flags) or short_cluster(flags, "B") or short_cluster(flags, "C"):
            raise Deny("force-creating or force-switching branches is not allowed")
        # -b/-c take the new branch name (consumed by scan), so pos holds only a start point
        creating = short_cluster(flags, "b") or short_cluster(flags, "c") or any(long_name(f) == "--create" for f in flags)
        if creating and pos and not resolves_to_head(ctx, pos[0]):
            raise Deny("create branches at the current HEAD only")
        for s in specs:
            reason = ctx.protected_write(s, cwd)
            if reason:
                raise Deny(reason)
    elif sub == "fetch":
        if any(":" in p or p.startswith("+") for p in pos[1:]):
            raise Deny("fetching into local refs is not allowed; use `git fetch <remote>`")
    elif sub == "config":
        readonly = any(long_name(f) in ("--get", "--get-all", "--get-regexp", "--list", "--show-origin",
                                        "--show-scope", "--get-urlmatch") for f in flags) or "-l" in flags
        if any(long_name(f) == "--edit" for f in flags) or "-e" in flags:
            raise Deny("editing git configuration interactively is not allowed")
        if not readonly and pos and pos[0].lower().startswith(CONFIG_DENY):
            raise Deny("changing git aliases, hooks, remotes, branches, or includes is not allowed")
    elif sub == "remote":
        if pos and pos[0] in ("add", "set-url", "rename", "remove", "rm", "set-head", "set-branches", "prune"):
            raise Deny("changing git remotes is not allowed in a plan-swarm repository")
    elif sub == "symbolic-ref":
        if len(pos) > 1 or any(long_name(f) == "--delete" for f in flags) or short_cluster(flags, "d"):
            raise Deny("rewriting symbolic refs is not allowed")
    if sub in ("rm", "mv", "restore", "checkout", "stash", "clean") :
        for p in pos + specs:
            reason = ctx.protected_write(p, cwd)
            if reason and ("approvals.md" in reason or "swarm.md" in reason or "git directory" in reason):
                raise Deny(reason)


def check_gh(tokens):
    args = [t for t in tokens[1:]]
    head2 = " ".join(a for a in args if not a.startswith("-"))[:40]
    words = [a for a in args if not a.startswith("-")]
    if words[:2] in (["pr", "merge"], ["pr", "ready"]) or (words[:2] == ["pr", "review"] and "--approve" in args):
        raise Deny("merging or approving pull requests is for people on GitHub")
    if words[:1] == ["release"] and words[1:2] and words[1] in ("create", "upload", "delete", "edit"):
        raise Deny("releases are created with `git tag` after `approve release`")
    if words[:1] == ["repo"] and words[1:2] and words[1] in ("sync", "delete", "edit", "rename", "archive"):
        raise Deny("changing the repository on GitHub is for people")
    if words[:1] == ["api"]:
        method = next((args[i + 1] for i, a in enumerate(args[:-1]) if a in ("-X", "--method")), "GET")
        if method.upper() != "GET" or any(a in ("-f", "-F", "--field", "--raw-field", "--input") for a in args):
            raise Deny("only read-only `gh api` calls are allowed")
    return head2


def check_bash(ctx, command, cwd):
    try:
        commands = simple_commands(command)
    except ValueError:
        if re.search(r"\bgit\b|\.git|approvals\.md|swarm\.md|plan-swarm|approve\.py", command):
            raise Deny("could not parse this command safely; run git and file commands on their own")
        return
    invocations = []
    staged_by_command = False
    for m in REDIRECT.finditer(command):
        target = m.group(2)
        if "$" in target or "`" in target:
            raise Deny("cannot verify a write whose target uses a variable or command substitution; use a literal path")
        reason = ctx.protected_write(target, cwd)
        if reason:
            raise Deny(reason)
    for cmd in commands:
        env, rest = split_env(cmd)
        for assignment in env:
            if any(w in assignment for w in FORBIDDEN_WORDS):
                raise Deny("the plan-swarm control plane's internals are not run or touched by agents")
            value = assignment.split("=", 1)[1]
            if (_inside(_norm(os.path.join(cwd, os.path.expanduser(value))), ctx.gitdir)
                    or any(w in value for w in FORBIDDEN_WORDS + ("approvals.md", "swarm.md"))):
                raise Deny("variables may not point at the git directory, the ledger, or plans/swarm.md")
        if rest and os.path.basename(rest[0]) in GIT_WRAPPERS:
            idx = next((i for i, t in enumerate(rest) if os.path.basename(t) == "git"), None)
            if idx is not None:
                if len(rest) == idx + 1 or os.path.basename(rest[0]) == "xargs":
                    raise Deny("git must be run directly with its subcommand, not through xargs or a wrapper")
                rest = rest[idx:]
        if rest and rest[0] == "cd":
            target = os.path.expanduser(rest[1]) if len(rest) > 1 else os.path.expanduser("~")
            cwd = os.path.normpath(os.path.join(cwd, target))
            if _inside(_norm(cwd), ctx.gitdir):
                raise Deny("working inside the git directory is not allowed")
            continue
        if rest and rest[0] == "export" and any(GIT_ENV_DENY.match(t) for t in rest[1:]):
            raise Deny("exporting GIT_* repository or configuration variables is not allowed")
        prog = os.path.basename(rest[0]) if rest else ""
        parsed = parse_git(rest)
        visible = strip_messages(rest) if parsed else rest
        for tok in visible:
            if any(w in tok for w in FORBIDDEN_WORDS):
                raise Deny("the plan-swarm control plane's internals are not run or touched by agents "
                           "(use `python3 \"$PLAN_LIB/health.py\" --status` to inspect it)")
        for tok in visible:
            if tok.startswith("-") and not tok.startswith("--git-dir") and not tok.startswith("--work-tree"):
                continue
            if _inside(_norm(os.path.join(cwd, os.path.expanduser(tok.split("=", 1)[-1]))), ctx.gitdir) and prog != "git":
                raise Deny("the git directory belongs to git and the plan-swarm control plane; agents may not touch it")
        if prog in INTERPRETERS and any(any(w in t for w in INTERPRETER_WORDS) or GIT_DIR_MENTION.search(t)
                                        for t in rest[1:]):
            raise Deny("scripts may not read or write the ledger, plans/swarm.md, or the git directory")
        in_place = prog in ("sed", "perl") and any(t.startswith("-i") or t == "--in-place" for t in rest)
        for i, tok in enumerate(rest):
            target = None
            bare = tok.lstrip("0123456789&")
            if bare.startswith(">"):
                target = bare.lstrip(">|") or (rest[i + 1] if i + 1 < len(rest) else "")
            elif i > 0 and not tok.startswith("-") and (prog in WRITERS or in_place):
                target = tok
            if target and ("$" in target or "`" in target):
                raise Deny("cannot verify a write whose target uses a variable or command substitution; "
                           "use a literal path")
            if target:
                reason = ctx.protected_write(target, cwd)
                if reason:
                    raise Deny(reason)
        if prog == "gh":
            check_gh(rest)
        if parsed:
            sub, args, opts = parsed
            if sub in ("add", "stage", "rm", "mv", "apply", "checkout", "restore", "update-index"):
                staged_by_command = True
            invocations.append((sub, args, opts, env, cwd))
        else:
            words = [t for t in rest if t not in WRAPPERS]
            text = " ".join(words)
            if re.search(r"(^|[\s/`$(])git\b", text) and GATED_WORDS.search(text):
                raise Deny("run git commands directly, not through another command, so they can be checked")
    nonce_ops = [sub for sub, args, _opts, _env, _cwd in invocations
                 if sub in ("commit", "push") or (sub == "tag" and scan("tag", args)[1])]
    if len(nonce_ops) > 1:
        raise Deny("run commit, push, and tag as separate commands so each gets its own approval check")
    contexts = {}
    for sub, args, opts, env, here_cwd in invocations:
        root = sg.repo_root(here_cwd) if os.path.isdir(here_cwd) else ctx.root
        if root not in contexts:
            if root == ctx.root:
                contexts[root] = ctx
            else:
                try:
                    cfg, store = load(root)
                except swarmdoc.SwarmDocError as err:
                    cfg, store = swarmdoc.validate_config({"version": 1}), sg.store_dir(root)
                    contexts[root] = Context(root, cfg, store, invalid=err)
                else:
                    contexts[root] = Context(root, cfg, store) if cfg else None
        here = contexts[root]
        if here is None:
            continue  # another repository that plan-swarm does not manage
        check_git(here, sub, args, opts, env, here_cwd, staged_by_command)
        if here is not ctx:
            ctx.actions.extend(here.actions)
            here.actions = []


MESSAGE_OPTS = ("-m", "--message", "-F", "--file")


def strip_messages(cmd):
    """Drop commit/tag message values so prose in a message never trips a check."""
    out, skip = [], False
    for tok in cmd:
        if skip:
            skip = False
            continue
        if tok in MESSAGE_OPTS:
            skip = True
            continue
        if tok.startswith("--message=") or (tok.startswith("-") and not tok.startswith("--") and len(tok) > 2
                                           and tok[-1] == "m"):
            skip = True  # clusters like -am / -qm take the next token as the message
            out.append(tok)
            continue
        if tok.startswith("-m") and len(tok) > 2 and not tok.startswith("--"):
            continue
        out.append(tok)
    return out


def check_write(ctx, file_path):
    if not file_path:
        return
    reason = ctx.protected_write(file_path, ctx.root)
    if reason:
        raise Deny(reason)


MILESTONE_REF = re.compile(rf"active_milestones/({sg.MONIKER})(?![a-z0-9._-])")
WORKFLOW_ENGINEER = re.compile(r"""type_name\s*=\s*["'](?:[\w.-]+:)?engineer["']""", re.I)
PHRASE_INSIDE = re.compile(r"\bapprove\s+(intent|spec|plan|commit|pr|release)\s+\S", re.I)


def _as_list(value):
    """Antigravity passes typed JSON args; tolerate a JSON-encoded string too."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return value if isinstance(value, list) else []


def _require_plan(ctx, text):
    for m in MILESTONE_REF.finditer(text or ""):
        moniker = m.group(1).rstrip(".")
        if not any(r["kind"] == "plan" for r in sg.read_ledger(ctx.main_root, moniker)):
            raise Deny(f"engineers cannot start on {moniker} before the plan is approved. "
                       f"Ask the user to type exactly: approve plan {moniker}")


def subagent_specs(args):
    return [s for s in _as_list(args.get("Subagents")) if isinstance(s, dict)]


def workflow_script(args):
    script = args.get("Script") or ""
    path = args.get("ScriptPath") or ""
    if not script and path and os.path.isfile(path):
        with open(path, encoding="utf-8", errors="replace") as fh:
            script = fh.read(1024 * 1024)
    return script


def check_dispatch(ctx, tool, args):
    """Refuse dispatching an engineer on a milestone whose plan is not approved."""
    if tool == "invoke_subagent":
        for spec in subagent_specs(args):
            agent = str(spec.get("TypeName") or "").strip().lower()
            if agent.split(":")[-1].strip() == "engineer":
                _require_plan(ctx, str(spec.get("Prompt") or ""))
    elif tool == "run_workflow":
        script = workflow_script(args)
        if WORKFLOW_ENGINEER.search(script):
            _require_plan(ctx, script)


def check_forgery(tool, args):
    """Refuse planting an approval phrase as somebody else's input (all repositories)."""
    import approve  # local import: approve imports gate's neighbours only

    if tool == "run_command":
        return
    texts = []
    if tool == "invoke_subagent":
        texts = [str(s.get("Prompt") or "") for s in subagent_specs(args)]
    elif tool == "send_message":
        texts = [str(args.get("Message") or "")]
    elif tool == "run_workflow":
        texts = [workflow_script(args)]
        texts += re.findall(r"""["']([^"'\n]{8,120})["']""", texts[0])
    if any(approve.parse(antigravity.user_request_text(t)) for t in texts):
        raise Deny("an approval phrase must be typed by a person in the top-level Antigravity conversation; "
                   "it cannot be sent as another agent's message")


# --------------------------------------------------------------------------
# entry points

def load(root):
    """Return (cfg, store), or (None, None) when the repository is not plan-swarm managed.

    Raises SwarmDocError when plans/swarm.md is invalid, or missing in a repository
    that swarm-init (or a previous session) marked as active."""
    if not os.path.exists(os.path.join(root, swarmdoc.CONFIG_PATH)):
        if sg.is_active(sg.store_dir(root, create=False)):
            raise swarmdoc.SwarmDocError("plans/swarm.md is missing in a plan-swarm repository "
                                         "(restore it; only a person may deactivate plan-swarm)")
        return None, None
    return swarmdoc.load_config(root), sg.store_dir(root)


def swarm_repo(root):
    store = sg.store_dir(root, create=False)
    return os.path.exists(os.path.join(root, swarmdoc.CONFIG_PATH)) or sg.is_active(store)


def pre_tool_use(event):
    """Check one Antigravity tool call. Returns the args overwrite dict (only when $PLAN_LIB
    was expanded) or None; raises Deny to block."""
    tool, args = antigravity.tool_call(event)
    check_forgery(tool, args)
    overwrite = None
    command = str(args.get("CommandLine") or "") if tool == "run_command" else ""
    if command:
        expanded = antigravity.expand_plan_lib(command)
        if expanded != command:
            overwrite = {"CommandLine": expanded}
    root, cfg, store, invalid = None, None, None, None
    for candidate in antigravity.candidate_dirs(event):
        root = sg.repo_root(candidate)
        try:
            cfg, store = load(root)
        except swarmdoc.SwarmDocError as err:
            cfg, store, invalid = swarmdoc.validate_config({"version": 1}), sg.store_dir(root), err
        if cfg is not None:
            break
    if cfg is None:
        return overwrite
    ctx = Context(root, cfg, store, invalid=invalid)
    if not sg.heartbeat_fresh(store, 60):
        sg.touch_heartbeat(store)
    _capture(event, root, store)
    if tool == "run_command":
        cwd = args.get("Cwd") if isinstance(args.get("Cwd"), str) and args.get("Cwd") else root
        if _inside(_norm(cwd), ctx.gitdir):
            raise Deny("working inside the git directory is not allowed")
        # checked unexpanded: "$PLAN_LIB/x.py" is never a write target, and the
        # plugin's install path must not trip the word checks
        check_bash(ctx, command, cwd)
    elif tool in antigravity.WRITE_TOOLS:
        check_write(ctx, args.get(antigravity.WRITE_TOOLS[tool]))
    elif tool in ("invoke_subagent", "run_workflow"):
        check_dispatch(ctx, tool, args)
    try:
        for action in ctx.actions:
            action()
    except sg.NonceTaken as err:
        raise Deny(str(err))
    return overwrite


def _capture(event, root, store):
    """Mint an approval typed since the last model call (PreInvocation normally does it
    first); its message reaches the model at the next PreInvocation."""
    import approve  # local import: approve imports gate's neighbours only

    try:
        message = approve.capture(event, root)
    except Exception as err:  # capture problems never block the tool call itself
        message = f"plan-swarm: approval capture failed ({type(err).__name__}: {err})"
    if message:
        approve.stash(store, event.get("conversationId") or "", message)


def git_hook():
    """pre-commit / pre-merge-commit: allow only with the ticket layer 1 issued."""
    root = sg.repo_root()
    try:
        cfg, store = load(root)
    except swarmdoc.SwarmDocError as err:
        print(f"plan-swarm: {err}; commit refused", file=sys.stderr)
        return 1
    if cfg is None:
        return 0
    head, branch = sg.head(root), sg.branch(root)
    moniker, task = sg.swarm_branch(branch)
    staged = sg.changed_paths(root)
    common = sg.common_dir(root)
    if task and sg.is_linked_worktree(root) and _inside(
            _norm(root), _norm(os.path.join(os.path.dirname(common), ".swarm", "worktrees", moniker))):
        if any(os.path.basename(p) == "approvals.md" for p in staged):
            print("plan-swarm: WIP commits must not include approvals.md", file=sys.stderr)
            return 1
        return 0
    ticket = sg.take_ticket(store, head)
    if ticket:
        if ticket.get("plans_only") and any(not p.startswith("plans/") for p in staged):
            print("plan-swarm: this approval covers plans/ only, but the commit includes other files", file=sys.stderr)
            return 1
        return 0
    if moniker or task:
        print(f"plan-swarm: commits on {branch} need an approval phrase typed in Antigravity.", file=sys.stderr)
        return 1
    if cfg["delivery"]["mode"] == "local" and sg.heartbeat_fresh(store):
        print("plan-swarm: a swarm session is active in local mode, so commits need an approval phrase "
              "typed in Antigravity.", file=sys.stderr)
        return 1
    return 0


ZERO = "0" * 40
COMMIT_KINDS = ("intent", "spec", "plan", "commit")


def pre_push(remote, lines):
    """pre-push: every commit pushed to swarm/{m} must match an approval in the ledger.

    swarm/* and swarm-wip/* refs are always checked. Other branches and tags are
    checked only while a swarm session is active (fresh heartbeat), so people can
    push their own work when no Antigravity swarm session is running in the repository."""
    root = sg.repo_root()
    try:
        cfg, store = load(root)
    except swarmdoc.SwarmDocError as err:
        print(f"plan-swarm: {err}; push refused", file=sys.stderr)
        return 1
    if cfg is None:
        return 0
    session = sg.heartbeat_fresh(store)
    for line in lines:
        parts = line.split()
        if len(parts) != 4:
            continue
        local_ref, local_sha, remote_ref, remote_sha = parts
        name = remote_ref.replace("refs/heads/", "")
        m, task = sg.swarm_branch(name)
        swarm_ref = bool(m) and remote_ref.startswith("refs/heads/")
        if not swarm_ref and not session:
            continue  # people push their own branches and tags when no swarm session is active
        if local_sha.strip("0") == "":
            print(f"plan-swarm: deleting {remote_ref} is not allowed", file=sys.stderr)
            return 1
        if remote_ref.startswith("refs/tags/"):
            tag = remote_ref[len("refs/tags/"):]
            if not sg.allowance(store, f"push-tag-{tag}"):
                print(f"plan-swarm: pushing tag {tag} needs a fresh `approve release {tag}`", file=sys.stderr)
                return 1
            continue
        if not m or task:
            print(f"plan-swarm: {name} is not pushed while a plan-swarm session is active in this repository"
                  if not m else f"plan-swarm: worktree branch {name} is never pushed", file=sys.stderr)
            return 1
        if remote_sha.strip("0") and not sg.git_ok("merge-base", "--is-ancestor", remote_sha, local_sha, cwd=root):
            print(f"plan-swarm: {name} would be rewritten (not a fast-forward)", file=sys.stderr)
            return 1
        rng = f"{remote_sha}..{local_sha}" if remote_sha.strip("0") else local_sha
        extra = [] if remote_sha.strip("0") else ["--not", f"--remotes={remote}"]
        commits = sg.git("rev-list", rng, *extra, cwd=root).split()
        ledger = sg.parse_ledger(sg.git("show", f"{local_sha}:plans/active_milestones/{m}/approvals.md", cwd=root)
                                 or "")
        # intent/spec/plan/commit rows authorize a commit; a `pr` row authorizes only the
        # ledger-only commit that records it
        heads = [r["head"] for r in ledger if r["head"] and r["kind"] in COMMIT_KINDS]
        pr_heads = [r["head"] for r in ledger if r["head"] and r["kind"] == "pr"]
        for c in commits:
            parents = sg.git("rev-list", "--parents", "-n", "1", c, cwd=root).split()[1:]
            ok = len(parents) == 1 and (any(parents[0].startswith(h) for h in heads) or (
                any(parents[0].startswith(h) for h in pr_heads) and ledger_only_commit(root, m, c)))
            if not ok:
                subject = sg.git("log", "-1", "--format=%h %s", c, cwd=root)
                print(f"plan-swarm: commit {subject} on {name} has no matching approval in approvals.md",
                      file=sys.stderr)
                return 1
        if not remote_sha.strip("0"):
            working = sg.read_ledger(root, m)
            tips = [local_sha]
            if ledger_only_commit(root, m, local_sha):
                tips.append(sg.git("rev-parse", "--verify", "--quiet", f"{local_sha}^", cwd=root))
            if not any(r["kind"] == "pr" and any(t.startswith(r["head"]) for t in tips if t) for r in working):
                print(f"plan-swarm: opening the PR for {m} needs `approve pr {m}` at this commit", file=sys.stderr)
                return 1
    return 0


def main(argv):
    if "--git-hook" in argv:
        try:
            return git_hook()
        except Exception as err:  # fail closed
            print(f"plan-swarm: internal error in the commit hook ({err}); commit refused", file=sys.stderr)
            return 1
    if "--pre-push" in argv:
        i = argv.index("--pre-push")
        remote = argv[i + 1] if len(argv) > i + 1 else "origin"
        try:
            return pre_push(remote, sys.stdin.read().splitlines())
        except Exception as err:  # fail closed
            print(f"plan-swarm: internal error in the push hook ({err}); push refused", file=sys.stderr)
            return 1
    event = {}
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("event is not an object")
        overwrite = pre_tool_use(event)
    except Deny as err:
        print(antigravity.deny(str(err)))
        return 0
    except Exception as err:  # fail closed inside plan-swarm repositories
        try:
            managed = isinstance(event, dict) and any(
                swarm_repo(sg.repo_root(d)) for d in antigravity.candidate_dirs(event))
        except Exception:
            managed = True
        if managed:
            print(antigravity.deny(f"internal error in the gate ({type(err).__name__}: {err}); refusing this "
                              "tool call. Report it to the user."))
        return 0
    if overwrite:
        # "allow" is a no-op in Antigravity apart from carrying the rewritten arguments,
        # so the user's own permission settings still decide whether the command runs
        print(json.dumps({"decision": "allow", "overwrite": overwrite}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
