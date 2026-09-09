#!/usr/bin/env python3
"""Exercise the exporter in a temporary clone of the pinned base; no project mutations."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

SCRIPT = Path(__file__).with_name("export_patch.py")


def run(*command, cwd=None, env=None, ok=True):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True)
    if ok and result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    if not ok and not result.returncode:
        raise AssertionError("command unexpectedly succeeded")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".")
    args = parser.parse_args()
    project = Path(args.project).resolve()
    base = json.loads((project / "patches/series.json").read_text())["base"]
    with tempfile.TemporaryDirectory(prefix="test-patch-maker-") as temp:
        root = Path(temp)
        fixture, checkout = root / "project", root / "work"
        (fixture / "patches").mkdir(parents=True)
        catalog = {"base": base, "features": [{"name": "base_dep"}, {"name": "dep", "requires": ["base_dep"]}, {"name": "feature", "requires": ["dep"]}]}
        (fixture / "patches/series.json").write_text(json.dumps(catalog))
        dep = b"diff --git a/dependency.txt b/dependency.txt\nnew file mode 100644\n--- /dev/null\n+++ b/dependency.txt\n@@ -0,0 +1 @@\n+dependency only\n"
        (fixture / "patches/dep.patch").write_bytes(dep)
        (fixture / "patches/base_dep.patch").write_bytes(dep.replace(b"dependency.txt", b"base-dependency.txt"))
        run("git", "clone", "--shared", "--no-checkout", str(project / "llama.cpp"), str(checkout))
        run("git", "checkout", "--detach", base, cwd=checkout)
        run("git", "apply", str(fixture / "patches/base_dep.patch"), cwd=checkout)
        run("git", "apply", str(fixture / "patches/dep.patch"), cwd=checkout)
        (checkout / "new file.txt").write_text("feature text\n")
        (checkout / "new.bin").write_bytes(bytes(range(256))*4)
        original_license = (checkout / "LICENSE").read_bytes()
        (checkout / "LICENSE").unlink()
        command = ["python3", str(SCRIPT), "--project", str(fixture), "--checkout", str(checkout), "--feature", "feature"]
        files = ["--files", "new file.txt", "new.bin", "LICENSE"]
        index_before = (checkout / ".git/index").read_bytes()
        run(*command, *files)
        output = fixture / "patches/feature.patch"
        patch = output.read_bytes()
        assert b"GIT binary patch" in patch and b"dependency.txt" not in patch
        assert (checkout / ".git/index").read_bytes() == index_before
        # Reconstruct dependency + feature with an independent temporary index.
        env = dict(os.environ, GIT_INDEX_FILE=str(root / "verify-index"))
        run("git", "read-tree", base, cwd=checkout, env=env)
        run("git", "apply", "--cached", str(fixture / "patches/base_dep.patch"), cwd=checkout, env=env)
        run("git", "apply", "--cached", str(fixture / "patches/dep.patch"), cwd=checkout, env=env)
        run("git", "apply", "--cached", str(output), cwd=checkout, env=env)
        run("git", "diff", "--quiet", cwd=checkout, env=env)
        assert run("git", "show", ":new.bin", cwd=checkout, env=env).stdout == bytes(range(256))*4
        assert run("git", "show", ":dependency.txt", cwd=checkout, env=env).stdout == b"dependency only\n"
        run("git", "show", ":LICENSE", cwd=checkout, env=env, ok=False)
        # Refusals must preserve the prior output and real index.
        run(*command, "--files", "new.bin", "LICENSE", ok=False)
        (checkout / "README.md").write_text("omitted tracked edit\n")
        run(*command, *files, ok=False)
        (checkout / "README.md").write_bytes(run("git", "show", "HEAD:README.md", cwd=checkout).stdout)
        run(*command, "--requires", "unknown", *files, ok=False)
        run(*command, "--files", ".", ok=False)
        assert output.read_bytes() == patch
        assert (checkout / ".git/index").read_bytes() == index_before
        # New dependent features use explicit --requires and keep dependencies out of the export.
        new_command = command[:-1] + ["new_feature", "--requires", "dep"]
        run(*new_command, *files)
        assert (fixture / "patches/new_feature.patch").read_bytes() == patch
        # The real managed checkout guard is based on resolved paths, including symlinks.
        (fixture / "llama.cpp").symlink_to(checkout, target_is_directory=True)
        run(*command, *files, ok=False)
        (fixture / "llama.cpp").unlink()
        # Existing staged work is never used as an implicit export baseline.
        run("git", "add", "--", "new file.txt", cwd=checkout)
        staged_index = (checkout / ".git/index").read_bytes()
        run(*command, *files, ok=False)
        assert (checkout / ".git/index").read_bytes() == staged_index
        assert output.read_bytes() == patch
        assert original_license
    print("Exporter checks passed: dependencies, additions, binary data, deletion, reconstruction, omissions, managed paths and index preservation.")


if __name__ == "__main__":
    main()
