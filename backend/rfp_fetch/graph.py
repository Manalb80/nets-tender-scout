"""Microsoft Graph access for the SharePoint RFP folder. Plain HTTP, no AI.

Authentication, first match wins:
  1. App-only (recommended for a scheduled job): GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET.
     Needs an Azure AD app registration with the Microsoft Graph *application* permission
     Files.Read.All (or Sites.Read.All), granted by a tenant admin ("admin consent").
  2. A ready access token in GRAPH_ACCESS_TOKEN (delegated, e.g. from `az account get-access-token
     --resource https://graph.microsoft.com`). Useful for a one-off test; it expires in about an hour.

Which folder, first match wins:
  1. SHAREPOINT_DRIVE_ID + SHAREPOINT_RFP_ITEM_ID   (exact; ids never change when the folder is renamed)
  2. SHAREPOINT_RFP_SHARE_URL                        (a sharing link; resolved through /shares/{id}/driveItem)
  3. SHAREPOINT_DRIVE_ID + SHAREPOINT_RFP_ROOT       (a path from the drive root, e.g.
                                                      "NETS-Karachi Presales-Technical Proposals/RFP")
"""
import base64
import logging
import os
import time
from typing import Callable, Dict, Iterator, List, Optional
from urllib.parse import quote

log = logging.getLogger("rfp_fetch.graph")
GRAPH = "https://graph.microsoft.com/v1.0"


class GraphError(Exception):
    """A Graph call failed. `hint` says what to change, in plain words."""

    def __init__(self, message: str, status: Optional[int] = None, hint: str = ""):
        super().__init__(message + (" | " + hint if hint else ""))
        self.status, self.hint = status, hint


def _hint(status: int) -> str:
    return {
        401: "The token was refused. Check GRAPH_TENANT_ID, GRAPH_CLIENT_ID and GRAPH_CLIENT_SECRET, or renew GRAPH_ACCESS_TOKEN.",
        403: "Access denied. The app registration needs the application permission Files.Read.All (or Sites.Read.All) "
             "with admin consent, or the signed-in user needs access to the folder.",
        404: "Folder or file not found. Check SHAREPOINT_DRIVE_ID / SHAREPOINT_RFP_ITEM_ID, the share link, or SHAREPOINT_RFP_ROOT. "
             "App-only tokens cannot always resolve a personal sharing link: use the drive id and item id instead.",
        429: "Graph is throttling requests; the job will retry on its next run.",
    }.get(status, "")


def share_id(url: str) -> str:
    """Graph's encoding of a sharing URL: 'u!' + unpadded base64url of the URL."""
    return "u!" + base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")


def token_provider_from_env() -> Callable[[], str]:
    tenant, client, secret = (os.environ.get(k, "").strip() for k in ("GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET"))
    if tenant and client and secret:
        import msal  # imported here so tests and dry runs on fixtures need no msal
        app = msal.ConfidentialClientApplication(client, authority="https://login.microsoftonline.com/" + tenant,
                                                 client_credential=secret)

        def get() -> str:
            res = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
            if "access_token" not in res:
                raise GraphError("Could not get an app-only token: %s" % res.get("error_description", res.get("error")),
                                 401, _hint(401))
            return res["access_token"]
        return get
    token = os.environ.get("GRAPH_ACCESS_TOKEN", "").strip()
    if token:
        return lambda: token
    raise GraphError("No Graph credentials.", None,
                     "Set GRAPH_TENANT_ID, GRAPH_CLIENT_ID and GRAPH_CLIENT_SECRET (app-only), or GRAPH_ACCESS_TOKEN.")


class GraphClient:
    def __init__(self, token: Callable[[], str], session=None, retries: int = 3):
        import requests
        self.token, self.http, self.retries = token, session or requests.Session(), retries

    def _get(self, url: str, stream: bool = False):
        for attempt in range(self.retries):
            r = self.http.get(url, headers={"Authorization": "Bearer " + self.token()}, timeout=120, stream=stream)
            if r.status_code in (429, 503, 504) and attempt < self.retries - 1:
                wait = int(r.headers.get("Retry-After", "5") or 5)
                log.warning("Graph %s, retrying in %ss", r.status_code, wait)
                time.sleep(min(wait, 60))
                continue
            if r.status_code >= 400:
                raise GraphError("GET %s failed: %s %s" % (url.split("?")[0], r.status_code, r.text[:200]), r.status_code, _hint(r.status_code))
            return r
        raise GraphError("GET %s kept failing" % url, None)

    def resolve_folder(self, env=os.environ) -> Dict:
        drive, item = env.get("SHAREPOINT_DRIVE_ID", "").strip(), env.get("SHAREPOINT_RFP_ITEM_ID", "").strip()
        share, root = env.get("SHAREPOINT_RFP_SHARE_URL", "").strip(), env.get("SHAREPOINT_RFP_ROOT", "").strip().strip("/")
        if drive and item:
            d = self._get("%s/drives/%s/items/%s" % (GRAPH, drive, item)).json()
        elif share:
            d = self._get("%s/shares/%s/driveItem" % (GRAPH, share_id(share))).json()
        elif drive and root:
            d = self._get("%s/drives/%s/root:/%s" % (GRAPH, drive, quote(root))).json()
        else:
            raise GraphError("No RFP folder configured.", None,
                             "Set SHAREPOINT_DRIVE_ID + SHAREPOINT_RFP_ITEM_ID, or SHAREPOINT_RFP_SHARE_URL, or SHAREPOINT_DRIVE_ID + SHAREPOINT_RFP_ROOT.")
        if "folder" not in d:
            raise GraphError("The configured item is not a folder: %s" % d.get("name"), None)
        return {"drive_id": (d.get("parentReference") or {}).get("driveId") or drive, "item_id": d["id"],
                "name": d.get("name"), "web_url": d.get("webUrl")}

    def list_files(self, drive_id: str, folder_id: str, recursive: bool = False, _path: str = "") -> Iterator[Dict]:
        url = "%s/drives/%s/items/%s/children?$top=200&$select=id,name,size,file,folder,eTag,cTag,lastModifiedDateTime,webUrl,parentReference" % (GRAPH, drive_id, folder_id)
        while url:
            page = self._get(url).json()
            for it in page.get("value", []):
                if "folder" in it:
                    if recursive:
                        yield from self.list_files(drive_id, it["id"], True, _path + it["name"] + "/")
                    continue
                if "file" not in it:
                    continue
                yield {"item_id": it["id"], "drive_id": drive_id, "name": it["name"], "path": _path + it["name"],
                       "size": int(it.get("size") or 0), "etag": it.get("eTag"), "ctag": it.get("cTag"),
                       "modified": it.get("lastModifiedDateTime"), "web_url": it.get("webUrl"),
                       "sha256": ((it.get("file") or {}).get("hashes") or {}).get("sha256Hash")}
            url = page.get("@odata.nextLink")

    def download(self, drive_id: str, item_id: str) -> bytes:
        return self._get("%s/drives/%s/items/%s/content" % (GRAPH, drive_id, item_id)).content


def listing_from_file(path: str) -> List[Dict]:
    """Offline listing for tests and dry runs: a JSON list of files as list_files yields them."""
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f)
