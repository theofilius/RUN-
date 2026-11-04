"""data/ kept in a private Supabase Storage bucket, for the hosted app.

The analysis keeps reading and writing plain files in data/. When the app runs with
DATA_STORE=supabase, it
  - pulls the bucket into data/ once when the server process starts (a hosted
    server starts with an empty disk), and
  - after every page run, uploads the files that run changed and deletes the ones
    it removed (see app/main.py).
One page run at a time (LOCK): the runner's settings (src/athlete.py) are shared by
the whole process, so two visitors must not interleave.

Settings, from the environment or .env (Streamlit Cloud: the app's Secrets):
  SUPABASE_URL         https://<project>.supabase.co
  SUPABASE_SECRET_KEY  the project's secret (service_role) key - server side only
  SUPABASE_BUCKET      default run-data; created private if missing
  DATA_STORE           supabase to sync from the app; anything else keeps data/ local

From the command line (the keys are enough, DATA_STORE is not needed):
  python -m src.cloud upload     copy your data/ into the bucket (first time)
  python -m src.cloud download   copy the bucket into data/ (backup, or work locally)
"""

import json
import os
import sys
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from src.env import env_value

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data"
MANIFEST = ".cloud-manifest.json"            # remote versions this disk has; never uploaded
SKIP = {MANIFEST, ".DS_Store"}
DEFAULT_BUCKET = "run-data"
PAGE = 1000
LOCK = threading.RLock()
_pulled = False


class Storage:
    """The few Supabase Storage calls we need, over plain HTTP."""

    def __init__(self, url, key, bucket=DEFAULT_BUCKET):
        self.url, self.key, self.bucket = url.rstrip("/"), key, bucket

    def call(self, method, path, body=None, data=None, headers=None):
        headers = {"apikey": self.key, **(headers or {})}
        if self.key.startswith("eyJ"):        # a legacy service_role JWT; new sb_secret_ keys go in apikey only
            headers["Authorization"] = f"Bearer {self.key}"
        if body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        request = Request(f"{self.url}/storage/v1/{path}", data=data, method=method, headers=headers)
        with urlopen(request, timeout=60) as response:
            return response.read()

    def ensure_bucket(self):
        try:
            self.call("GET", f"bucket/{self.bucket}")
        except HTTPError as error:
            if error.code not in (400, 404):
                raise
            self.call("POST", "bucket", {"id": self.bucket, "name": self.bucket, "public": False})

    def list_all(self, prefix=""):
        """{path: version} of every file under prefix (folders are walked)."""
        files, offset = {}, 0
        while True:
            items = json.loads(self.call("POST", f"object/list/{self.bucket}",
                                         {"prefix": prefix, "limit": PAGE, "offset": offset,
                                          "sortBy": {"column": "name", "order": "asc"}}))
            for item in items:
                path = f"{prefix}/{item['name']}" if prefix else item["name"]
                if item.get("id") is None:                       # a folder
                    files.update(self.list_all(path))
                elif item["name"] != ".emptyFolderPlaceholder":
                    meta = item.get("metadata") or {}
                    files[path] = meta.get("eTag") or item.get("updated_at")
            if len(items) < PAGE:
                return files
            offset += PAGE

    def download(self, path):
        return self.call("GET", f"object/{self.bucket}/{quote(path)}")

    def upload(self, path, content):
        self.call("POST", f"object/{self.bucket}/{quote(path)}", data=content,
                  headers={"x-upsert": "true", "Content-Type": "application/octet-stream"})

    def delete(self, paths):
        if paths:
            self.call("DELETE", f"object/{self.bucket}", {"prefixes": list(paths)})


def storage(root=ROOT):
    """A Storage from the settings, or None without them."""
    url, key = env_value("SUPABASE_URL", root), env_value("SUPABASE_SECRET_KEY", root)
    if not (url and key):
        return None
    return Storage(url, key, env_value("SUPABASE_BUCKET", root) or DEFAULT_BUCKET)


def active(root=ROOT):
    """True when the app itself keeps data/ in Supabase (DATA_STORE=supabase)."""
    return (env_value("DATA_STORE", root) or "").lower() == "supabase" and storage(root) is not None


def snapshot(data_root=DATA_ROOT):
    """{relative path: (size, modified)} of every file in data_root."""
    data_root, files = Path(data_root), {}
    for folder, _, names in os.walk(data_root):
        for name in names:
            if name in SKIP:
                continue
            path = Path(folder) / name
            stat = path.stat()
            files[path.relative_to(data_root).as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return files


def load_manifest(data_root):
    path = Path(data_root) / MANIFEST
    return json.loads(path.read_text()) if path.exists() else {}


def save_manifest(data_root, manifest):
    Path(data_root).mkdir(parents=True, exist_ok=True)
    (Path(data_root) / MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True))


def pull(store, data_root=DATA_ROOT):
    """Make data_root match the bucket: new or changed files down, files deleted remotely removed.

    Local files the bucket has never had are left alone. Returns the number of files changed.
    """
    data_root, manifest = Path(data_root), load_manifest(data_root)
    remote, changed = store.list_all(), 0
    for path, version in remote.items():
        local = data_root / path
        if local.exists() and manifest.get(path) == version:
            continue
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(store.download(path))
        manifest[path], changed = version, changed + 1
    for path in [p for p in manifest if p not in remote]:
        (data_root / path).unlink(missing_ok=True)
        del manifest[path]
        changed += 1
    save_manifest(data_root, manifest)
    return changed


def push(store, before, data_root=DATA_ROOT):
    """Upload what changed since the snapshot `before`, delete what was removed. Returns paths touched."""
    data_root, after = Path(data_root), snapshot(data_root)
    changed = [p for p, stamp in after.items() if before.get(p) != stamp]
    removed = [p for p in before if p not in after]
    if not (changed or removed):
        return []
    manifest = load_manifest(data_root)
    for path in changed:
        store.upload(path, (data_root / path).read_bytes())
        manifest[path] = None            # our own upload: its remote version is fetched again on the next start
    store.delete(removed)
    for path in removed:
        manifest.pop(path, None)
    save_manifest(data_root, manifest)
    return changed + removed


def pull_once(store, data_root=DATA_ROOT):
    """Pull when this server process starts (the first page run), not on every click."""
    global _pulled
    if not _pulled:
        pull(store, data_root)
        _pulled = True


def upload_all(store, data_root=DATA_ROOT):
    """First upload: every file in data_root into the bucket."""
    store.ensure_bucket()
    files = sorted(snapshot(data_root))
    for i, path in enumerate(files, 1):
        store.upload(path, (Path(data_root) / path).read_bytes())
        print(f"  {i}/{len(files)} {path}")
    save_manifest(data_root, {p: None for p in files})
    return files


def main(argv):
    from src import users

    store = storage()
    if store is None or len(argv) != 2 or argv[1] not in ("upload", "download"):
        sys.exit(__doc__ if store else "Put SUPABASE_URL and SUPABASE_SECRET_KEY in .env first.")
    if argv[1] == "download":
        store.ensure_bucket()
        print(f"{pull(store)} files updated in {DATA_ROOT}")
        return
    missing = [u["id"] for u in users.load(DATA_ROOT)["users"] if not users.has_password(u)]
    if missing:
        sys.exit("Give every runner a password before going online, so nobody else can open their data:\n"
                 + "\n".join(f"  python -m src.users password {m}" for m in missing))
    files = upload_all(store)
    print(f"{len(files)} files uploaded to the {store.bucket} bucket.")


if __name__ == "__main__":
    main(sys.argv)
