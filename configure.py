#!/usr/bin/env python3
"""Select local feature patches without creating upstream commits."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
REPO = ROOT / "llama.cpp"
STATE = ROOT / ".patch-state"


def git(*args, data=None, env=None):
    result = subprocess.run(["git", "-C", str(REPO), *args], input=data,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    if result.returncode:
        raise RuntimeError(result.stderr.decode().strip() or "git " + " ".join(args) + " failed")
    return result.stdout


def tree(base, patches):
    with tempfile.TemporaryDirectory() as directory:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(directory) / "index"))
        git("read-tree", base, env=env)
        for patch in patches:
            git("apply", "--cached", "--whitespace=nowarn", "-", data=patch.encode(), env=env)
        return git("write-tree", env=env).decode().strip()


def matches(expected):
    with tempfile.TemporaryDirectory() as directory:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(directory) / "index"))
        git("read-tree", expected, env=env)
        try:
            git("diff", "--quiet", env=env)
            return True
        except RuntimeError:
            return False


def toggle_feature(features, selected, name):
    selected = set(selected)
    if name in selected:
        selected.remove(name)
        while True:
            invalid = {f["name"] for f in features if f["name"] in selected
                       and set(f.get("requires", [])) - selected}
            if not invalid:
                break
            selected -= invalid
    else:
        selected.add(name)
        while True:
            required = {dep for f in features if f["name"] in selected
                        for dep in f.get("requires", [])}
            if required <= selected:
                break
            selected |= required
    return selected


def interactive_menu(features, selected):
    import curses
    import textwrap

    def menu(screen):
        nonlocal selected
        selected = set(selected)
        names = {f["name"] for f in features}
        query, cursor, offset = "", 0, 0
        curses.set_escdelay(25)
        curses.curs_set(0)
        highlight = curses.A_REVERSE | curses.A_BOLD
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1)
            highlight = curses.color_pair(1) | curses.A_BOLD
        screen.keypad(True)
        while True:
            height, width = screen.getmaxyx()
            screen.erase()

            def put(row, column, text, style=0):
                if 0 <= row < height and column < width - 1:
                    try:
                        screen.addnstr(row, column, text, width - column - 1, style)
                    except curses.error:
                        pass  # A resize can occur between measuring and drawing.

            if height < 12 or width < 40:
                put(0, 0, "Enlarge terminal (40 columns, 12 rows).")
                put(1, 0, "Esc: cancel")
                screen.refresh()
                if screen.get_wch() in ("\x1b", "\x03"):
                    return None
                continue
            visible = [f for f in features if query.casefold() in
                       (f["name"] + " " + f["description"]).casefold()]
            cursor = min(cursor, max(0, len(visible) - 1))
            capacity = height - 10
            offset = max(0, min(offset, cursor))
            if cursor >= offset + capacity:
                offset = cursor - capacity + 1
            put(0, 0, "Enable/Disable Patches", curses.A_BOLD)
            put(1, 0, "Space toggles a patch. Enter applies your selection.", curses.A_DIM)
            put(3, 0, "> " + (query or "Type to search patches"),
                0 if query else curses.A_DIM)
            name_width = min(max((len(f["name"]) for f in features), default=0), width // 2)
            for index in range(offset, min(len(visible), offset + capacity)):
                feature = visible[index]
                label = f"[{'x' if feature['name'] in selected else ' '}] {feature['name']:<{name_width}}  {feature['description']}"
                put(5 + index - offset, 0, label,
                    highlight if index == cursor else 0)
            if not visible:
                put(5, 0, "No matching patches.", curses.A_DIM)
            if visible:
                feature = visible[cursor]
                detail = feature["description"]
                if feature.get("requires"):
                    detail += " | Requires: " + ", ".join(feature["requires"])
                for index, line in enumerate(textwrap.wrap(detail, width - 1)[:2]):
                    put(height - 5 + index, 0, line, curses.A_DIM)
            put(height - 3, 0, f"{len(selected)}/{len(features)} enabled · Dependencies selected automatically", curses.A_DIM)
            put(height - 2, 0, "↑/↓ Move  Space Toggle  Ctrl+A All  Ctrl+N None")
            put(height - 1, 0, "Enter Apply  Esc Cancel  Ctrl+U Clear search")
            screen.refresh()
            key = screen.get_wch()
            if key in ("\x1b", "\x03"):
                return None
            if key in ("\n", "\r", curses.KEY_ENTER):
                return selected
            if key == curses.KEY_UP:
                cursor = max(0, cursor - 1)
            elif key == curses.KEY_DOWN:
                cursor = min(max(0, len(visible) - 1), cursor + 1)
            elif key == curses.KEY_HOME:
                cursor = 0
            elif key == curses.KEY_END:
                cursor = max(0, len(visible) - 1)
            elif key == curses.KEY_NPAGE:
                cursor = min(max(0, len(visible) - 1), cursor + capacity)
            elif key == curses.KEY_PPAGE:
                cursor = max(0, cursor - capacity)
            elif key == " " and visible:
                selected = toggle_feature(features, selected, visible[cursor]["name"])
            elif key == "\x01":
                selected = set(names)
            elif key == "\x0e":
                selected = set()
            elif key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                query, cursor, offset = query[:-1], 0, 0
            elif key == "\x15":
                query, cursor, offset = "", 0, 0
            elif isinstance(key, str) and key.isprintable() and key != " ":
                query, cursor, offset = query + key, 0, 0

    try:
        return curses.wrapper(menu)
    except curses.error as error:
        raise RuntimeError("Cannot open terminal selector; check TERM or use --all, --none or --enable") from error


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true", help="enable all features")
    group.add_argument("--none", action="store_true", help="disable all features")
    group.add_argument("--enable", nargs="+", metavar="FEATURE", help="set the exact enabled feature list")
    group.add_argument("--list", action="store_true", help="show active features")
    args = parser.parse_args()
    catalog = json.loads((ROOT / "patches/series.json").read_text())
    features = catalog["features"]
    names = [f["name"] for f in features]
    STATE.mkdir(exist_ok=True)
    with (STATE / "lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state_file = STATE / "selection.json"
        previous = json.loads(state_file.read_text()) if state_file.exists() else {"enabled": [], "patches": [], "base": catalog["base"]}
        pending = STATE / "selection.pending.json"
        if pending.exists():
            interrupted = json.loads(pending.read_text())
            if matches(tree(interrupted["base"], interrupted["patches"])):
                pending.replace(state_file)
                previous = interrupted
            elif matches(tree(previous["base"], previous["patches"])):
                pending.unlink()
            else:
                raise RuntimeError("Interrupted switch and local edits detected. Restore the managed files to the saved or pending selection before retrying.")
        selected = set(previous["enabled"])
        if args.list:
            for feature in features:
                print(f"[{'x' if feature['name'] in selected else ' '}] {feature['name']}: {feature['description']}")
            return
        if args.all:
            selected = set(names)
        elif args.none:
            selected = set()
        elif args.enable:
            selected = set(args.enable)
        else:
            if not sys.stdin.isatty() or not sys.stdout.isatty():
                parser.error("interactive mode requires a terminal; use --all, --none or --enable")
            selected = interactive_menu(features, selected)
            if selected is None:
                print("Selection cancelled.")
                return
        if selected - set(names):
            raise RuntimeError("Unknown features: " + ", ".join(sorted(selected - set(names))))
        for feature in features:
            if feature["name"] in selected and set(feature.get("requires", [])) - selected:
                raise RuntimeError(feature["name"] + " requires: " + ", ".join(feature["requires"]))
        base = catalog["base"]
        if git("rev-parse", "HEAD").decode().strip() != base or (previous["patches"] and previous["base"] != base):
            raise RuntimeError("Checkout/base mismatch. Disable patches before changing the pinned upstream revision.")
        git("diff", "--cached", "--exit-code", "--quiet")
        old_tree = tree(base, previous["patches"])
        if not matches(old_tree):
            raise RuntimeError("Local edits differ from the active patch selection.")
        patches = [(ROOT / "patches" / (name + ".patch")).read_text()
                   for name in names if name in selected]
        new_tree = tree(base, patches)
        transition = git("diff", "--binary", old_tree, new_tree)
        new_state = {"base": base, "enabled": [n for n in names if n in selected], "patches": patches}
        if transition:
            git("apply", "--check", "--whitespace=nowarn", "-", data=transition)
        temporary = STATE / "selection.pending.tmp"
        temporary.write_text(json.dumps(new_state, indent=2) + "\n")
        temporary.replace(pending)
        if transition:
            git("apply", "--whitespace=nowarn", "-", data=transition)
        pending.replace(state_file)
        print("Enabled: " + (", ".join(new_state["enabled"]) or "none (upstream)"))


if __name__ == "__main__":
    try:
        run()
    except (RuntimeError, OSError, ValueError, EOFError) as error:
        sys.exit(f"Error: {error}\nNo reset or clean was performed. Preserve local edits before retrying.")
