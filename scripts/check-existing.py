#!/usr/bin/env python3
"""Skip an already completed publisher-managed release; never overwrite it."""
import json
import os
import subprocess


def classify_return(code: int, stdout: str, stderr: str, tag: str, zip_name: str) -> bool:
    """True means skip. Fail on any unexpected release or API error."""
    if code != 0:
        if "release not found" in stderr.lower() or "http 404" in stderr.lower():
            print("No matching release yet: a build is needed")
            return False
        raise RuntimeError(f"Cannot check GitHub release {tag}: {stderr.strip()}")
    release = json.loads(stdout)
    if release.get("isDraft") or "portable-release-publisher:managed:v2" not in release.get("body", ""):
        raise RuntimeError(f"Tag {tag} already exists but is not a complete shared-publisher-managed release")
    names = {asset["name"] for asset in release.get("assets", [])}
    if zip_name not in names or "SHA256SUMS.txt" not in names:
        raise RuntimeError(f"Managed release {tag} is incomplete: expected {zip_name} and checksums")
    print("This exact website configuration is already published. Skipping compilation.")
    return True


def main():
    plan = json.load(open("work/plan.json", encoding="utf-8"))
    result = subprocess.run(["gh", "release", "view", plan["releaseTag"],
                             "--repo", os.environ["GITHUB_REPOSITORY"],
                             "--json", "body,assets,isDraft"], capture_output=True, text=True)
    skip = classify_return(result.returncode, result.stdout, result.stderr,
                           plan["releaseTag"], plan["zipName"])
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        out.write(f"skip={'true' if skip else 'false'}\n")


if __name__ == "__main__":
    main()
