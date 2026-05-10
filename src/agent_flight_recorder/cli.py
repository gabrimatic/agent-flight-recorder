from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .exceptions import AFRError, GitError, SessionError
from .git import is_git_repo
from .paths import config_path, latest_report_path, repo_root
from .config import load_config
from .report import render_markdown
from .session import (
    analyze_repository,
    ensure_project,
    init_project,
    load_manifest,
    run_command_in_active_session,
    run_wrapped_session,
    save_manifest,
    session_status,
    start_manual_session,
    stop_session,
)
from .utils import atomic_write_text, json_dump


LEVEL_TO_SCORE = {
    "low": 20,
    "medium": 50,
    "high": 79,
    "critical": 100,
}


def strip_command_separator(command: list[str]) -> list[str]:
    if command and command[0] == "--":
        return command[1:]
    return command


def cmd_init(args: argparse.Namespace) -> int:
    root = repo_root(Path.cwd())
    init_project(root, force=args.force)
    print(f"Initialized Agent Flight Recorder at {root / '.agent-flight'}")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    root = repo_root(Path.cwd())
    command = strip_command_separator(list(args.command or []))
    if command:
        manifest = run_wrapped_session(
            root,
            argv=command,
            session_id=args.session_id,
            note=args.note,
            capture_output=not args.interactive,
        )
        risk = manifest.get("risk") or {}
        print(f"Agent flight session complete: {manifest['session_id']}")
        print(f"Risk: {risk.get('level')} ({risk.get('score')}/100)")
        print(f"Report: {latest_report_path(root)}")
        return int((manifest.get("commands") or [{}])[-1].get("exit_code") or 0)
    manifest = start_manual_session(root, session_id=args.session_id, note=args.note)
    print(f"Started agent flight session: {manifest['session_id']}")
    print("Run commands through `afr run -- <command>` when possible, then finish with `afr stop`.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    root = repo_root(Path.cwd())
    command = strip_command_separator(list(args.command or []))
    if not command:
        raise SessionError("Missing command. Use `afr run -- <command>`.")
    manifest = run_command_in_active_session(root, argv=command, capture_output=not args.interactive)
    last = (manifest.get("commands") or [{}])[-1]
    print(f"Recorded command in session {manifest['session_id']}: exit {last.get('exit_code')}")
    return int(last.get("exit_code") or 0)


def cmd_stop(args: argparse.Namespace) -> int:
    root = repo_root(Path.cwd())
    manifest = stop_session(root, session_id=args.session_id)
    risk = manifest.get("risk") or {}
    print(f"Stopped agent flight session: {manifest['session_id']}")
    print(f"Risk: {risk.get('level')} ({risk.get('score')}/100)")
    print(f"Report: {latest_report_path(root)}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root = repo_root(Path.cwd())
    status = session_status(root)
    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True))
        return 0
    print(f"Agent Flight directory: {status['agent_flight_dir']}")
    if status["active"]:
        print(f"Active session: {status['active']['session_id']} started {status['active']['started_at']}")
    else:
        print("Active session: none")
    print(f"Latest manifest: {status['latest_manifest'] or 'none'}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    root = repo_root(Path.cwd())
    manifest_path = Path(args.manifest).resolve() if args.manifest else None
    manifest = load_manifest(root, session_id=args.session_id, manifest_path=manifest_path)
    if args.format == "json":
        output = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    else:
        output = render_markdown(manifest)
    if args.output:
        atomic_write_text(Path(args.output), output)
        print(f"Wrote report: {args.output}")
    else:
        sys.stdout.write(output)
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    root = repo_root(Path.cwd())
    manifest = analyze_repository(root, base_ref=args.base_ref, session_id=args.session_id)
    if args.output:
        content = json.dumps(manifest, indent=2, sort_keys=True) + "\n" if args.json else render_markdown(manifest)
        atomic_write_text(Path(args.output), content)
    risk = manifest.get("risk") or {}
    print(f"Analysis session: {manifest['session_id']}")
    print(f"Risk: {risk.get('level')} ({risk.get('score')}/100)")
    print(f"Report: {args.output or latest_report_path(root)}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    root = repo_root(Path.cwd())
    manifest_path = Path(args.manifest).resolve() if args.manifest else None
    manifest = load_manifest(root, session_id=args.session_id, manifest_path=manifest_path)
    risk = manifest.get("risk") or {}
    score = int(risk.get("score") or 0)
    max_score = args.max_score
    if args.max_level:
        max_score = LEVEL_TO_SCORE[args.max_level]
    failures: list[str] = []
    if score > max_score:
        failures.append(f"risk score {score} exceeds allowed score {max_score}")
    summary = risk.get("summary") or {}
    if args.require_tests_for_high_risk and str(risk.get("level")) in {"high", "critical"}:
        if not summary.get("successful_tests_recorded"):
            failures.append("high/critical risk change has no recorded successful test command")
    if args.require_command_log and summary.get("changed_files", 0) and not summary.get("commands", 0):
        failures.append("changed files exist but no command log was recorded")
    if failures:
        print("Agent Flight verification failed:")
        for item in failures:
            print(f"- {item}")
        return 1
    print(f"Agent Flight verification passed: {risk.get('level')} ({score}/100)")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    data: dict[str, Any] = {
        "version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "git_on_path": bool(shutil.which("git")),
        "inside_git_repo": is_git_repo(Path.cwd()),
    }
    if data["inside_git_repo"]:
        root = repo_root(Path.cwd())
        cfg = config_path(root)
        data["repo_root"] = str(root)
        data["config_path"] = str(cfg)
        data["config_exists"] = cfg.exists()
        if cfg.exists():
            try:
                load_config(cfg)
                data["config_ok"] = True
            except AFRError as exc:
                data["config_ok"] = False
                data["config_error"] = str(exc)
        else:
            data["config_ok"] = None
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        for key, value in data.items():
            print(f"{key}: {value}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="afr",
        description="Black-box recorder for coding-agent code changes.",
    )
    parser.add_argument("--version", action="store_true", help="Print version and exit.")
    sub = parser.add_subparsers(dest="command_name")

    p_init = sub.add_parser("init", help="Initialize .agent-flight in the current git repository.")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing config.json.")
    p_init.set_defaults(func=cmd_init)

    p_start = sub.add_parser("start", help="Start a manual session or wrap a command.")
    p_start.add_argument("--session-id", help="Use a specific session id.")
    p_start.add_argument("--note", help="Attach a human note to the session.")
    p_start.add_argument("--interactive", action="store_true", help="Let the child process inherit the terminal instead of capturing output.")
    p_start.add_argument("--capture-output", action="store_true", help="Compatibility flag; output is captured by default unless --interactive is set.")
    p_start.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after --.")
    p_start.set_defaults(func=cmd_start)

    p_run = sub.add_parser("run", help="Run and record a command inside an active manual session.")
    p_run.add_argument("--interactive", action="store_true", help="Let the child process inherit the terminal instead of capturing output.")
    p_run.add_argument("command", nargs=argparse.REMAINDER, help="Command to run after --.")
    p_run.set_defaults(func=cmd_run)

    p_stop = sub.add_parser("stop", help="Stop the active manual session and generate a report.")
    p_stop.add_argument("--session-id", help="Stop a specific session instead of the active session.")
    p_stop.set_defaults(func=cmd_stop)

    p_status = sub.add_parser("status", help="Show current Agent Flight state.")
    p_status.add_argument("--json", action="store_true", help="Print JSON.")
    p_status.set_defaults(func=cmd_status)

    p_report = sub.add_parser("report", help="Print or write a report from a manifest.")
    p_report.add_argument("--session-id", help="Read a specific session.")
    p_report.add_argument("--manifest", help="Read a manifest path directly.")
    p_report.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p_report.add_argument("--output", help="Write report to this path instead of stdout.")
    p_report.set_defaults(func=cmd_report)

    p_analyze = sub.add_parser("analyze", help="Analyze the current git diff, useful in CI.")
    p_analyze.add_argument("--base-ref", help="Base ref for diff analysis, e.g. origin/main.")
    p_analyze.add_argument("--session-id", help="Use a specific session id.")
    p_analyze.add_argument("--output", help="Write markdown or JSON report to this path.")
    p_analyze.add_argument("--json", action="store_true", help="When --output is provided, write JSON instead of markdown.")
    p_analyze.set_defaults(func=cmd_analyze)

    p_verify = sub.add_parser("verify", help="Fail if a manifest violates merge-gate rules.")
    p_verify.add_argument("--session-id", help="Verify a specific session.")
    p_verify.add_argument("--manifest", help="Verify a manifest path directly.")
    p_verify.add_argument("--max-score", type=int, default=79, help="Fail if risk score is greater than this value. Default: 79.")
    p_verify.add_argument("--max-level", choices=sorted(LEVEL_TO_SCORE), help="Alternative to --max-score.")
    p_verify.add_argument("--require-tests-for-high-risk", action="store_true", help="Fail high/critical manifests with no successful recorded test command.")
    p_verify.add_argument("--require-command-log", action="store_true", help="Fail changed manifests with no recorded command log.")
    p_verify.set_defaults(func=cmd_verify)

    p_doctor = sub.add_parser("doctor", help="Print environment diagnostics.")
    p_doctor.add_argument("--json", action="store_true", help="Print JSON.")
    p_doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    try:
        return int(args.func(args))
    except (AFRError, GitError) as exc:
        print(f"afr: error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("afr: interrupted", file=sys.stderr)
        return 130
