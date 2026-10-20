"""The app's download list across releases: every version is built once, and later lists keep pointing at it.
  python -I tools/feed.py todo <refs.tsv> <previous index.json>
      prints the refs.tsv lines (from latest_refs.py) whose version has no build in the previous list yet, and every
      followed branch (a catalogue entry's "refs"), which can have moved on
  python -I tools/feed.py merge <new index.json> <previous index.json> <refs.tsv> <out index.json> [status ...]
      new builds plus the previous ones still wanted: a version stays while refs.tsv lists it. A firmware
      missing from refs.tsv entirely (its GitHub lookup failed, or this run built other statuses) keeps its
      builds while its catalogue status is ready, untested or one of the statuses given. Sorted by firmware (in
      firmwares.json's order), newest version first, then model.
A missing or empty previous file counts as an empty list."""
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = ["X4 Pro", "X4 Classic", "X3"]


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return []
    if not text.strip():
        return []
    feed = json.loads(text)
    if feed.get("schema") != 1:
        sys.exit(f"feed: {path}: unknown schema {feed.get('schema')!r}")
    return feed["builds"]


def refs(path):
    rows = []
    for line in open(path, encoding="utf-8"):
        p = line.rstrip("\r\n").split("\t")
        if len(p) >= 2 and p[0] and p[1]:
            rows.append((p[0], p[1]))
    return rows


def todo(refs_path, previous_path):
    built = {(b["repo"], b["ref"]) for b in load(previous_path)}
    # branches a catalogue entry follows ("refs") move on: built again every run, the new build replaces the old
    catalogue = json.load(open(os.path.join(HERE, "firmwares.json"), encoding="utf-8"))["firmwares"]
    followed = {(f["repo"], r) for f in catalogue for r in f.get("refs", [])}
    for repo, ref in refs(refs_path):
        if (repo, ref) not in built or (repo, ref) in followed:
            print(f"{repo}\t{ref}")


def merge(new_path, previous_path, refs_path, out_path, statuses):
    wanted = refs(refs_path)
    rank = {r: i for i, r in enumerate(wanted)}  # latest_refs.py lists each firmware's versions newest first
    looked_up = {repo for repo, _ in wanted}
    catalogue = json.load(open(os.path.join(HERE, "firmwares.json"), encoding="utf-8"))["firmwares"]
    still_offered = {f["repo"] for f in catalogue if f["repo"] and f["status"] in {"ready", "untested", *statuses}}
    new, previous = load(new_path), load(previous_path)
    ids = {b["id"] for b in new}
    kept = [b for b in previous if b["id"] not in ids and (
        (b["repo"], b["ref"]) in rank or (b["repo"] not in looked_up and b["repo"] in still_offered))]
    builds = new + kept
    order = {f["repo"]: i for i, f in enumerate(catalogue)}  # firmwares.json lists them in the order to show
    builds.sort(key=lambda b: (order.get(b["repo"], len(order)), b["name"].casefold(), b["repo"], rank.get((b["repo"], b["ref"]), len(rank)),
                               MODELS.index(b["model"]) if b["model"] in MODELS else len(MODELS)))
    feed = {"schema": 1, "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "builds": builds}
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(feed, f, indent=1)
        f.write("\n")
    dropped = sum(1 for b in previous if b["id"] not in ids) - len(kept)
    print(f"feed: {len(new)} new, {len(kept)} kept, {dropped} dropped; "
          f"{len({(b['repo'], b['ref']) for b in builds})} versions of {len({b['repo'] for b in builds})} firmwares in {out_path}")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "todo":
        todo(*sys.argv[2:])
    elif len(sys.argv) >= 6 and sys.argv[1] == "merge":
        merge(*sys.argv[2:6], sys.argv[6:])
    else:
        sys.exit(__doc__)
