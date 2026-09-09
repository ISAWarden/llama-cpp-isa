#!/usr/bin/env python3
"""Export one feature from a disposable pinned checkout using a temporary Git index."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile


def git(checkout, *args, env=None, data=None):
    result = subprocess.run(["git", "-C", str(checkout), *args], input=data,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace").strip() or "git " + " ".join(args) + " failed")
    return result.stdout


def dependencies(catalog, feature, requested):
    features = catalog["features"]
    by_name = {f["name"]: f for f in features}
    if len(by_name) != len(features):
        raise ValueError("duplicate feature names in catalog")
    if feature in by_name:
        direct = by_name[feature].get("requires", [])
        if requested is not None and set(requested) != set(direct):
            raise ValueError("--requires disagrees with the existing catalog entry")
    else:
        direct = requested or []
    needed, visiting = set(), {feature}

    def visit(name):
        if name in visiting:
            raise ValueError("cyclic feature dependency: " + name)
        if name in needed:
            return
        if name not in by_name:
            raise ValueError("unknown dependency: " + name)
        visiting.add(name)
        for dep in by_name[name].get("requires", []):
            visit(dep)
        visiting.remove(name)
        needed.add(name)

    for name in direct:
        visit(name)
    ordered = [f["name"] for f in features if f["name"] in needed]
    seen = set()
    for name in ordered:
        if set(by_name[name].get("requires", [])) - seen:
            raise ValueError("dependencies must precede dependents in series.json")
        seen.add(name)
    if feature in by_name:
        before = {f["name"] for f in features[:features.index(by_name[feature])]}
        if needed - before:
            raise ValueError("feature precedes its dependencies in series.json")
    return ordered


def export(args):
    project, checkout = Path(args.project).resolve(), Path(args.checkout).resolve()
    if checkout == (project / "llama.cpp").resolve():
        raise ValueError("use a disposable checkout, not the managed llama.cpp checkout")
    if Path(git(checkout, "rev-parse", "--show-toplevel").decode().strip()).resolve() != checkout:
        raise ValueError("--checkout must name the Git checkout root")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", args.feature):
        raise ValueError("feature names use lowercase letters, digits and underscores")
    catalog = json.loads((project / "patches/series.json").read_text())
    base = git(checkout, "rev-parse", "--verify", catalog["base"] + "^{commit}").strip()
    if git(checkout, "rev-parse", "HEAD").strip() != base:
        raise ValueError("checkout HEAD must match the catalog base; no feature commits")
    git(checkout, "diff", "--cached", "--quiet", "HEAD")
    paths = []
    for name in args.files:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or ".git" in path.parts or not path.parts:
            raise ValueError("expected an explicit repository-relative file: " + name)
        full = checkout / path
        if full.is_dir() and not full.is_symlink():
            raise ValueError("list files explicitly, not directories: " + name)
        paths.append(str(path))
    deps = dependencies(catalog, args.feature, args.requires)
    with tempfile.TemporaryDirectory(prefix="patch-export-") as temporary:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / "index"), GIT_LITERAL_PATHSPECS="1")
        git(checkout, "read-tree", base.decode(), env=env)
        for name in deps:
            git(checkout, "apply", "--cached", "--whitespace=nowarn", "-", env=env,
                data=(project / "patches" / (name + ".patch")).read_bytes())
        baseline = git(checkout, "write-tree", env=env).decode().strip()
        git(checkout, "add", "--all", "--force", "--", *paths, env=env)
        # Catch omitted tracked edits and missing dependencies; unrelated scratch files belong outside this checkout.
        git(checkout, "diff", "--quiet", env=env)
        omitted = git(checkout, "ls-files", "--others", "--exclude-standard", "-z", env=env)
        if omitted:
            raise ValueError("untracked files omitted from --files: " + ", ".join(os.fsdecode(p) for p in omitted.split(b"\0") if p))
        git(checkout, "diff", "--cached", "--check", baseline, env=env)
        patch = git(checkout, "diff", "--cached", "--binary", "--full-index", "--no-ext-diff",
                    "--no-textconv", baseline, env=env)
        if not patch:
            raise ValueError("empty feature diff against dependency baseline")
        result_tree = git(checkout, "write-tree", env=env).strip()
        git(checkout, "read-tree", baseline, env=env)
        git(checkout, "apply", "--cached", "-", env=env, data=patch)
        if git(checkout, "write-tree", env=env).strip() != result_tree:
            raise RuntimeError("exported patch does not reproduce the selected tree")
    output = project / "patches" / (args.feature + ".patch")
    if output.is_symlink():
        raise ValueError("patch output must not be a symlink")
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=output.name + ".", delete=False) as stream:
            temporary_name = stream.name
            stream.write(patch)
        os.chmod(temporary_name, output.stat().st_mode & 0o777 if output.exists() else 0o644)
        os.replace(temporary_name, output)
        temporary_name = None
    finally:
        if temporary_name:
            os.unlink(temporary_name)
    print(json.dumps({"patch": str(output), "dependency_baseline": baseline,
                      "dependencies": deps, "bytes": len(patch)}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".", help="llama-cpp-isa root (default: current directory)")
    parser.add_argument("--checkout", required=True, help="disposable llama.cpp checkout at the pinned base")
    parser.add_argument("--feature", required=True)
    parser.add_argument("--requires", action="append", help="repeat for direct dependencies of a new feature; existing entries are inferred")
    parser.add_argument("--files", nargs="+", required=True, help="explicit relative files, including additions and deletions")
    args = parser.parse_args()
    try:
        export(args)
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Error: {error}\nPatch output was not replaced.\n")


if __name__ == "__main__":
    main()
