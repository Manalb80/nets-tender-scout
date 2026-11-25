"""Where Agent 1b finds RFP files. Every source yields the same file records and reads bytes on request,
so the engine never knows (or cares) where a file came from.

  LocalFolderSource  a local folder: the OneDrive-synced copy of the SharePoint RFP folder, or a staging
                     folder people save downloads into. Needs no Azure app registration. The default.
  GraphSource        the SharePoint folder itself through Microsoft Graph. Plug it in once IT has granted an
                     app registration (see graph.py); nothing else changes.
  ListingSource      a JSON listing plus a folder of files, for offline tests.

A file record holds: item_id, name, path (relative to the folder), size, modified (ISO time), sha256 and,
for Graph, drive_id, ctag and web_url.
"""
import hashlib
import json
import logging
import os
import shutil
import stat
import time
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional, Tuple

log = logging.getLogger("rfp_fetch.sources")

# Names that are never RFPs: partial downloads, Office lock files, OneDrive and OS clutter.
_SKIP_PREFIX = ("~$", ".~", "._", ".")
_SKIP_SUFFIX = (".tmp", ".part", ".partial", ".crdownload", ".download", ".opdownload", ".!ut", ".lnk")
_SKIP_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}
# Windows attributes that mark a OneDrive "online-only" placeholder: reading it would start a download.
_CLOUD_ONLY = 0x1000 | 0x40000 | 0x400000   # OFFLINE | RECALL_ON_OPEN | RECALL_ON_DATA_ACCESS


def skip_name(name: str) -> bool:
    n = name.lower()
    return n in _SKIP_NAMES or n.startswith(_SKIP_PREFIX) or n.endswith(_SKIP_SUFFIX)


def _iso_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class HashCache:
    """Remembers (size, mtime) -> sha256 per path, so unchanged files are not re-hashed on every run.
    Only an optimisation: the dashboard stays the record of what was sent."""

    def __init__(self, path: Optional[str]):
        self.path, self.rows, self.dirty = path, {}, False
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self.rows = json.load(f)
            except (OSError, ValueError):
                log.warning("Hash cache %s unreadable; starting fresh", path)

    def get(self, rel: str, size: int, mtime_ns: int) -> Optional[str]:
        r = self.rows.get(rel)
        return r["sha256"] if r and r.get("size") == size and r.get("mtime_ns") == mtime_ns else None

    def put(self, rel: str, size: int, mtime_ns: int, sha: str) -> None:
        self.rows[rel] = {"size": size, "mtime_ns": mtime_ns, "sha256": sha}
        self.dirty = True

    def prune(self, keep: Iterable[str]) -> None:
        keep = set(keep)
        for k in [k for k in self.rows if k not in keep]:
            del self.rows[k]
            self.dirty = True

    def save(self) -> None:
        if self.path and self.dirty:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.rows, f, indent=0, sort_keys=True)
            os.replace(tmp, self.path)
            self.dirty = False


class LocalFolderSource:
    kind = "local"

    def __init__(self, root: str, recursive: bool = True, stable_seconds: float = 30, recheck_seconds: float = 2,
                 archive_dir: Optional[str] = None, cache: Optional[HashCache] = None, hydrate: bool = False,
                 clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep):
        if not root or not os.path.isdir(root):
            raise SourceError("RFP folder not found: %r" % root,
                              "Set RFP_WATCH_DIR to the synced RFP folder (in OneDrive: right-click the folder, "
                              "'Always keep on this device'), or to the staging folder people save RFPs into.")
        self.root = os.path.abspath(root)
        self.recursive, self.stable_seconds, self.recheck_seconds = recursive, stable_seconds, recheck_seconds
        self.archive_dir = os.path.abspath(archive_dir) if archive_dir else None
        self.cache, self.hydrate, self.clock, self.sleep = cache or HashCache(None), hydrate, clock, sleep
        self.waiting: List[Dict] = []      # files skipped this run, with the reason

    def describe(self) -> Dict:
        return {"kind": self.kind, "root": self.root, "name": os.path.basename(self.root)}

    def _walk(self) -> Iterable[Tuple[str, str]]:
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames if not skip_name(d)
                                 and not (self.archive_dir and os.path.abspath(os.path.join(dirpath, d)) == self.archive_dir))
            for fn in sorted(filenames):
                full = os.path.join(dirpath, fn)
                yield full, os.path.relpath(full, self.root).replace(os.sep, "/")
            if not self.recursive:
                break

    def list_files(self) -> List[Dict]:
        now, candidates = self.clock(), []
        for full, rel in self._walk():
            name = os.path.basename(full)
            if skip_name(name):
                continue
            try:
                st = os.stat(full)
            except OSError as e:
                self.waiting.append({"file": rel, "reason": "unreadable: %s" % e})
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            if getattr(st, "st_file_attributes", 0) & _CLOUD_ONLY and not self.hydrate:
                self.waiting.append({"file": rel, "reason": "online-only in OneDrive (set 'Always keep on this device', or RFP_HYDRATE=true)"})
                continue
            if st.st_size == 0:
                self.waiting.append({"file": rel, "reason": "empty, probably still being written"})
                continue
            if now - st.st_mtime < self.stable_seconds:
                self.waiting.append({"file": rel, "reason": "changed %ds ago; waiting until it has been still for %ds"
                                     % (max(0, now - st.st_mtime), self.stable_seconds)})
                continue
            candidates.append((full, rel, st))
        if candidates and self.recheck_seconds:
            self.sleep(self.recheck_seconds)   # one pause for all files: is anything still growing?
        out, seen = [], []
        for full, rel, st in candidates:
            try:
                st2 = os.stat(full)
                with open(full, "rb") as fh:     # Windows refuses this while another program holds the file
                    fh.read(1)
            except OSError as e:
                self.waiting.append({"file": rel, "reason": "in use: %s" % e.strerror})
                continue
            if (st2.st_size, st2.st_mtime_ns) != (st.st_size, st.st_mtime_ns):
                self.waiting.append({"file": rel, "reason": "still being written"})
                continue
            sha = self.cache.get(rel, st.st_size, st.st_mtime_ns)
            if not sha:
                sha = sha256_file(full)
                self.cache.put(rel, st.st_size, st.st_mtime_ns, sha)
            seen.append(rel)
            out.append({"item_id": "sha256:" + sha, "name": os.path.basename(full), "path": rel, "size": st.st_size,
                        "modified": _iso_ts(st.st_mtime), "sha256": sha, "abs_path": full})
        self.cache.prune(seen + [w["file"] for w in self.waiting])
        return out

    def read(self, f: Dict) -> bytes:
        with open(f["abs_path"], "rb") as fh:
            data = fh.read()
        if hashlib.sha256(data).hexdigest() != f["sha256"]:
            raise SourceError("%s changed while it was being read; it will be picked up next run" % f["path"])
        return data

    def archive(self, f: Dict, tender_id: str, mode: str) -> Optional[str]:
        """Copy or move a file the dashboard already holds into <archive>/<tender id>/. Returns the target."""
        if mode == "off" or not self.archive_dir:
            return None
        safe = "".join(c if c not in '\\/:*?"<>|' else "_" for c in f["name"])
        target_dir = os.path.join(self.archive_dir, tender_id)
        target = os.path.join(target_dir, safe)
        if os.path.exists(target):
            if sha256_file(target) == f["sha256"]:
                if mode == "move":
                    os.remove(f["abs_path"])
                    return target
                return None                          # already archived
            stem, ext = os.path.splitext(safe)
            target = os.path.join(target_dir, "%s.%s%s" % (stem, f["sha256"][:8], ext))
            if os.path.exists(target):
                if mode == "move":
                    os.remove(f["abs_path"])
                    return target
                return None
        os.makedirs(target_dir, exist_ok=True)
        tmp = target + ".partial"
        shutil.copy2(f["abs_path"], tmp)
        os.replace(tmp, target)
        if mode == "move":
            os.remove(f["abs_path"])
        return target


class GraphSource:
    """The SharePoint folder through Microsoft Graph. Needs credentials (see graph.py)."""
    kind = "graph"

    def __init__(self, recursive: bool = False):
        from .graph import GraphClient, token_provider_from_env
        self.g = GraphClient(token_provider_from_env())
        self.folder = self.g.resolve_folder()
        self.recursive, self.waiting = recursive, []

    def describe(self) -> Dict:
        return dict(self.folder, kind=self.kind)

    def list_files(self) -> List[Dict]:
        return list(self.g.list_files(self.folder["drive_id"], self.folder["item_id"], recursive=self.recursive))

    def read(self, f: Dict) -> bytes:
        return self.g.download(f["drive_id"], f["item_id"])

    def archive(self, f, tender_id, mode):
        return None    # SharePoint is the archive; nothing to move


class ListingSource:
    """Offline: a JSON listing (as list_files yields it) and a folder holding the files."""

    def __init__(self, listing: str, files_dir: Optional[str] = None, kind: str = "graph"):
        with open(listing, encoding="utf-8") as fh:
            self.files = json.load(fh)
        self.base = files_dir or os.path.dirname(os.path.abspath(listing))
        self.kind, self.waiting = kind, []

    def describe(self) -> Dict:
        return {"kind": self.kind, "root": self.base}

    def list_files(self) -> List[Dict]:
        return self.files

    def read(self, f: Dict) -> bytes:
        with open(os.path.join(self.base, f.get("path") or f["name"]), "rb") as fh:
            return fh.read()

    def archive(self, f, tender_id, mode):
        return None


class SourceError(Exception):
    def __init__(self, message: str, hint: str = ""):
        super().__init__(message + (" | " + hint if hint else ""))
        self.hint = hint
