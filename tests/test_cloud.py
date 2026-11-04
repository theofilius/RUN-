"""data/ in Supabase Storage (src/cloud.py) and passwords / login tokens (src/users.py)."""

import os
import time

from src import cloud, users


class FakeStorage:
    """The bucket in memory, with a new version for every upload."""

    def __init__(self):
        self.files, self.versions, self.n = {}, {}, 0

    def ensure_bucket(self):
        pass

    def list_all(self, prefix=""):
        return dict(self.versions)

    def download(self, path):
        return self.files[path]

    def upload(self, path, content):
        self.n += 1
        self.files[path], self.versions[path] = content, f"v{self.n}"

    def delete(self, paths):
        for path in paths:
            self.files.pop(path, None)
            self.versions.pop(path, None)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_a_new_server_gets_the_bucket_and_sends_back_only_what_changed(tmp_path):
    laptop, server, bucket = tmp_path / "laptop", tmp_path / "server", FakeStorage()
    write(laptop / "users.json", "{}")
    write(laptop / "programs" / "a" / "plans" / "week-1.pkl", "frozen")
    assert cloud.upload_all(bucket, laptop) == ["programs/a/plans/week-1.pkl", "users.json"]

    assert cloud.pull(bucket, server) == 2
    assert (server / "programs" / "a" / "plans" / "week-1.pkl").read_text() == "frozen"
    assert cloud.pull(bucket, server) == 0                       # nothing new: nothing downloaded

    before = cloud.snapshot(server)
    write(server / "programs.json", "new")                       # a page run adds one file
    assert cloud.push(bucket, before, server) == ["programs.json"]
    assert cloud.push(bucket, cloud.snapshot(server), server) == []

    before = cloud.snapshot(server)
    (server / "programs" / "a" / "plans" / "week-1.pkl").unlink()   # a program deleted
    assert cloud.push(bucket, before, server) == ["programs/a/plans/week-1.pkl"]
    assert "programs/a/plans/week-1.pkl" not in bucket.files
    assert cloud.MANIFEST not in bucket.files


def test_a_change_made_elsewhere_reaches_the_next_pull(tmp_path):
    bucket = FakeStorage()
    bucket.upload("users.json", b"old")
    bucket.upload("gone.csv", b"x")
    cloud.pull(bucket, tmp_path)
    bucket.upload("users.json", b"new")
    bucket.delete(["gone.csv"])
    write(tmp_path / "mine.txt", "never uploaded")
    cloud.pull(bucket, tmp_path)
    assert (tmp_path / "users.json").read_text() == "new"
    assert not (tmp_path / "gone.csv").exists()
    assert (tmp_path / "mine.txt").exists()                      # never in the bucket: left alone


def test_the_app_syncs_only_when_asked(tmp_path, monkeypatch):
    for name in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "DATA_STORE"):
        monkeypatch.delenv(name, raising=False)
    assert cloud.storage(tmp_path) is None and not cloud.active(tmp_path)
    (tmp_path / ".env").write_text("SUPABASE_URL=https://x.supabase.co\nSUPABASE_SECRET_KEY=k\n")
    assert cloud.storage(tmp_path).bucket == cloud.DEFAULT_BUCKET and not cloud.active(tmp_path)
    monkeypatch.setenv("DATA_STORE", "supabase")
    assert cloud.active(tmp_path)


def test_passwords_and_login_tokens(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_SECRET", raising=False)
    store = users.load(tmp_path)
    users.set_password(tmp_path, store, "tee", "lari-pagi-123")
    tee = users.find(users.load(tmp_path), "tee")
    assert "lari-pagi-123" not in str(tee)                        # only the hash is kept
    assert users.check_password(tee, "lari-pagi-123") and not users.check_password(tee, "wrong")

    secret = users.app_secret(tmp_path)
    assert secret == users.app_secret(tmp_path) and len(secret) == 64
    token = users.login_token(tee, secret)
    assert users.valid_token(tee, token, secret)
    assert not users.valid_token(tee, token, "another secret")
    assert not users.valid_token(tee, token, secret, now=time.time() + (users.TOKEN_DAYS + 1) * 86400)
    tampered = token[:-1] + ("1" if token.endswith("0") else "0")
    assert not users.valid_token(tee, tampered, secret)
    assert not users.valid_token(tee, None, secret) and not users.valid_token(tee, "junk", secret)

    users.set_password(tmp_path, store, "tee", "a-new-password")  # a new password ends old logins
    assert not users.valid_token(users.find(store, "tee"), token, secret)
    assert not users.valid_token(users.find(store, "tee"), users.login_token(tee, secret), secret)
    assert users.athlete(users.find(store, "tee")).name == "tee"


def test_app_secret_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_SECRET", "s3cret")
    assert users.app_secret(tmp_path) == "s3cret"
    assert not os.path.exists(tmp_path / users.SECRET_FILE)
