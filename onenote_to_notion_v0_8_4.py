#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
onenote_to_notion.py (v0.8.4)

Fixes vs 0.8.3:
- Notion upload "Content-Type must include a boundary": we no longer set Content-Type
  manually for the multipart send call; Requests will add the proper boundary.
- Minor: make sure save_state is present and not shadowed.
"""
import os, sys, re, time, json, hashlib, mimetypes, argparse
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup, NavigableString, Tag
import msal

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
NOTION_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
GRAPH_SCOPE = [s.strip() for s in os.getenv("MS_GRAPH_SCOPES","Notes.Read.All,Sites.Read.All").split(",")]
STATE_PATH = os.path.expanduser(os.getenv("ON2N_STATE", "~/.onenote2notion/state.json"))

ALLOWED_EXT = {".png",".jpg",".jpeg",".gif",".webp",".pdf",".txt",".csv",".docx",".xlsx",".pptx",".mp4",".mp3",".wav"}
CT_TO_EXT = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg",
    "image/gif": ".gif", "image/webp": ".webp",
    "application/pdf": ".pdf", "text/plain": ".txt", "text/csv": ".csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "video/mp4": ".mp4", "audio/mpeg": ".mp3", "audio/wav": ".wav",
    "image/svg+xml": ".png",
}

def md5(s:str)->str: return hashlib.md5(s.encode("utf-8")).hexdigest()
def H_ms(token:str)->Dict[str,str]: return {"Authorization": f"Bearer {token}"}
def H_notion(token:str, ct:str="application/json")->Dict[str,str]:
    return {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION, "accept": "application/json", "content-type": ct}
def H_notion_no_ct(token:str)->Dict[str,str]:
    return {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION, "accept": "application/json"}

# ---------- Content-type sniff ----------
def sniff_content_type(data: bytes) -> Optional[str]:
    if len(data) >= 12:
        b = data[:12]
        if b.startswith(b"\x89PNG\r\n\x1a\n"): return "image/png"
        if b.startswith(b"\xff\xd8\xff"): return "image/jpeg"
        if b.startswith(b"GIF87a") or b.startswith(b"GIF89a"): return "image/gif"
        if b.startswith(b"%PDF-"): return "application/pdf"
        if b[:4] == b"RIFF" and data[8:12] == b"WEBP": return "image/webp"
        if b[:2] == b"PK": return "application/zip"
    try:
        sample = data[:2000].decode("utf-8")
        ls = sample.lower()
        if "<svg" in ls: return "image/svg+xml"
        if "<html" in ls: return "text/html"
        return "text/plain"
    except UnicodeDecodeError:
        return None

def ext_from_filename(name: str) -> str:
    _, ext = os.path.splitext(name)
    return ext.lower()

def filename_for_ct(basename: str, content_type: str) -> str:
    name, _ = os.path.splitext(basename)
    ext = CT_TO_EXT.get(content_type) or mimetypes.guess_extension(content_type) or ".bin"
    if ext not in ALLOWED_EXT:
        if content_type.startswith("image/"):
            ext = ".png"; content_type = "image/png"
        elif content_type.startswith("text/"):
            ext = ".txt"; content_type = "text/plain"
        else:
            ext = ".pdf"; content_type = "application/pdf"
    if not name: name = "file"
    return f"{name}{ext}"

def coerce_ct_and_filename(data: bytes, ctype_header: Optional[str], url: str) -> Tuple[str, str]:
    header = (ctype_header or "").split(";")[0].strip() or None
    guessed = sniff_content_type(data)
    ext_url = ext_from_filename(os.path.basename(urlparse(url).path))

    chosen_ct = header
    if not chosen_ct or chosen_ct == "application/octet-stream":
        chosen_ct = guessed or ( "image/png" if ext_url in {".png",".jpg",".jpeg",".gif",".webp",".svg",".svgz"} else None )
    if not chosen_ct:
        chosen_ct = "application/pdf"

    basename = os.path.basename(urlparse(url).path) or "file"
    filename = filename_for_ct(basename, chosen_ct)
    return chosen_ct, filename

# ---------- State ----------
def load_state():
    try:
        if os.path.exists(STATE_PATH):
            return json.loads(open(STATE_PATH,"r",encoding="utf-8").read())
    except: pass
    return {"pages":{}}

def save_state(state: Dict[str,Any]):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH,"w",encoding="utf-8") as f:
        json.dump(state, f, indent=2)

# ---------- MSAL ----------
def ms_build_app(client_id: str, tenant_id: str):
    return msal.PublicClientApplication(client_id=client_id, authority=f"https://login.microsoftonline.com/{tenant_id}")

def ms_acquire_token_device_code(app) -> Dict[str, Any]:
    flow = app.initiate_device_flow(scopes=GRAPH_SCOPE)
    if "user_code" not in flow: raise RuntimeError(f"Device flow failed: {flow}")
    print("\\n=== Microsoft Sign-in ===")
    print("Go to:", flow['verification_uri'])
    print("Enter code:", flow['user_code'])
    print("Waiting for authentication..."); sys.stdout.flush()
    res = app.acquire_token_by_device_flow(flow)
    if "access_token" not in res: raise RuntimeError(f"Could not acquire token: {res}")
    return res

# ---------- Graph helpers ----------
def resolve_site_id_from_url(token: str, site_url: str) -> str:
    u = urlparse(site_url); host=u.netloc; path=u.path.lstrip("/")
    if path.startswith("sites/"):
        rel = path[len("sites/"):]
        api = f"{GRAPH_BASE}/sites/{host}:/sites/{rel}?$select=id,displayName"
    elif path.startswith("teams/"):
        rel = path[len("teams/"):]
        api = f"{GRAPH_BASE}/sites/{host}:/teams/{rel}?$select=id,displayName"
    else:
        api = f"{GRAPH_BASE}/sites/{host}?$select=id,displayName"
    r = requests.get(api, headers=H_ms(token)); r.raise_for_status(); return r.json()["id"]

def list_site_notebooks(token: str, site_id: str):
    url = f"{GRAPH_BASE}/sites/{site_id}/onenote/notebooks?$top=200"; out=[]
    while url:
        r=requests.get(url, headers=H_ms(token)); r.raise_for_status(); j=r.json()
        out += j.get("value",[]); url=j.get("@odata.nextLink")
    return out

def get_sections_from_notebook(token: str, notebook: Dict[str,Any]):
    sec_url = notebook.get("sectionsUrl")
    if not sec_url: raise RuntimeError("Notebook entry missing sectionsUrl")
    r=requests.get(sec_url+"?$top=200", headers=H_ms(token)); r.raise_for_status()
    return r.json().get("value", [])

def list_pages_for_section(token: str, section: Dict[str,Any], since: Optional[str]=None, verbose=False):
    purl = section.get("pagesUrl"); 
    if not purl: return []
    url = purl + "?$top=100"
    if since: url += f"&$filter=lastModifiedDateTime ge {since}T00:00:00Z"
    pages=[]
    while url:
        r=requests.get(url, headers=H_ms(token))
        if r.status_code>=400:
            if verbose: print("PagesUrl error, retry plain:", r.text[:300])
            r=requests.get(purl, headers=H_ms(token))
        r.raise_for_status()
        j=r.json(); pages += j.get("value",[]); url=j.get("@odata.nextLink")
    return pages

def fetch_page_html(token: str, site_id: str, page_id: str) -> str:
    r=requests.get(f"{GRAPH_BASE}/sites/{site_id}/onenote/pages/{page_id}/content", headers=H_ms(token)); r.raise_for_status()
    return r.text

def rewrite_resource_url_to_graph(site_id: str, href: str) -> Optional[str]:
    m = re.search(r"/onenote/resources/([^/\\?]+)", href)
    if not m: return None
    res_id = m.group(1)
    return f"{GRAPH_BASE}/sites/{site_id}/onenote/resources/{res_id}/content"

# ---------- Notion ops ----------
def notion_get_database(notion_token: str, db_id: str):
    r=requests.get(f"{NOTION_BASE}/databases/{db_id}", headers=H_notion(notion_token)); r.raise_for_status(); return r.json()

def notion_find_by_onenote_id(notion_token, db_id, prop_key, prop_type, on_id):
    props = requests.get(f"{NOTION_BASE}/databases/{db_id}", headers=H_notion(notion_token)).json().get("properties",{})
    if prop_type=="rich_text": f={"property":prop_key,"rich_text":{"equals":on_id}}
    elif prop_type=="url": f={"property":prop_key,"url":{"equals":on_id}}
    elif prop_type=="title": f={"property":prop_key,"title":{"equals":on_id}}
    else: f=None
    if not f: return None
    r=requests.post(f"{NOTION_BASE}/databases/{db_id}/query", headers=H_notion(notion_token), json={"filter":f}); r.raise_for_status()
    res=r.json().get("results",[]); return res[0]["id"] if res else None

def notion_create_page(notion_token, db_id, props, children):
    payload={"parent":{"database_id":db_id},"properties":props,"children":children[:100]}
    r=requests.post(f"{NOTION_BASE}/pages", headers=H_notion(notion_token), json=payload); r.raise_for_status()
    return r.json()["id"]

def notion_update_page(notion_token, page_id, props):
    r=requests.patch(f"{NOTION_BASE}/pages/{page_id}", headers=H_notion(notion_token), json={"properties":props}); r.raise_for_status()

def notion_append_children(notion_token, block_id, blocks):
    url=f"{NOTION_BASE}/blocks/{block_id}/children"
    i=0; last=None
    while i < len(blocks):
        payload={"children":blocks[i:i+50]}
        r=requests.patch(url, headers=H_notion(notion_token), json=payload); r.raise_for_status()
        last=r.json()
        i+=50; time.sleep(0.12)
    return last

def notion_upload_bytes(notion_token: str, filename: str, data: bytes, content_type: Optional[str]=None) -> Optional[str]:
    chosen_ct = (content_type or "").split(";")[0].strip() if content_type else None
    if not chosen_ct or chosen_ct == "application/octet-stream":
        chosen_ct, safe_name = coerce_ct_and_filename(data, chosen_ct, filename)
    else:
        safe_name = filename_for_ct(filename, chosen_ct)
    if len(data) > 20 * 1024 * 1024:
        print("[warn] file too large for single-part upload (>20MB):", safe_name)
        return None
    r = requests.post(f"{NOTION_BASE}/file_uploads", headers=H_notion(notion_token), json={"filename": safe_name, "content_type": chosen_ct})
    if r.status_code != 200:
        print("[warn] create file_upload failed:", r.text[:300]); return None
    file_upload_id = r.json().get("id")
    files = {"file": (safe_name, data, chosen_ct)}
    # IMPORTANT: don't set content-type manually -> let requests set boundary
    r2 = requests.post(f"{NOTION_BASE}/file_uploads/{file_upload_id}/send", headers=H_notion_no_ct(notion_token), files=files)
    if r2.status_code != 200:
        print("[warn] file send failed:", r2.text[:300]); return None
    return file_upload_id

def image_block_from_upload(file_upload_id: str):
    return {"object":"block","type":"image","image":{"type":"file_upload","file_upload":{"id": file_upload_id}}}
def file_block_from_upload(file_upload_id: str):
    return {"object":"block","type":"file","file":{"type":"file_upload","file_upload":{"id": file_upload_id}}}

# ---------- Rich text ----------
def build_rich_text(node: Tag) -> List[Dict[str,Any]]:
    parts: List[Dict[str,Any]] = []
    def push_text(text: str):
        if text: parts.append({"type":"text","text":{"content":text}})
    for child in node.children:
        if isinstance(child, NavigableString):
            push_text(str(child))
        elif isinstance(child, Tag) and child.name.lower()=="a":
            href = child.get("href")
            txt = child.get_text()
            parts.append({"type":"text","text":{"content":txt,"link":{"url":href}}})
        elif isinstance(child, Tag):
            parts.extend(build_rich_text(child))
    for p in parts:
        if p["type"]=="text" and len(p["text"]["content"])>2000:
            p["text"]["content"]=p["text"]["content"][:2000]
    return parts or [{"type":"text","text":{"content":""}}]

# ---------- HTML -> Notion ----------
def html_to_blocks_and_tables(html: str, site_id: str, ms_auth_header: Dict[str,str], notion_token: str):
    soup=BeautifulSoup(html, "html.parser")
    blocks: List[Dict[str,Any]] = []
    tables: List[List[List[str]]] = []

    def add_paragraph_rich(el): blocks.append({"object":"block","type":"paragraph","paragraph":{"rich_text":build_rich_text(el)}})
    def add_heading(level, el): k=f"heading_{level}"; blocks.append({"object":"block","type":k,k:{"rich_text":build_rich_text(el)}})
    def add_todo(el, checked=False): blocks.append({"object":"block","type":"to_do","to_do":{"rich_text":build_rich_text(el),"checked":checked}})
    def add_quote(el): blocks.append({"object":"block","type":"quote","quote":{"rich_text":build_rich_text(el)}})
    def add_code(text): blocks.append({"object":"block","type":"code","code":{"rich_text":[{"type":"text","text":{"content":text}}],"language":"text"}})

    def fetch_resource(url: str) -> Tuple[Optional[bytes], Optional[str], str]:
        if not url: return None, None, "file"
        orig_url = url
        if "/onenote/resources/" in url:
            fixed = rewrite_resource_url_to_graph(site_id, url)
            if fixed: url = fixed
        try:
            r=requests.get(url, headers=ms_auth_header); r.raise_for_status()
            raw = r.content
            header_ct = r.headers.get("Content-Type","").split(";")[0].strip() or None
            final_ct, safe_name = coerce_ct_and_filename(raw, header_ct, orig_url)
            return raw, final_ct, safe_name
        except Exception as e:
            print("[warn] media fetch failed:", e); return None, None, "file"

    def handle_images(el: Tag):
        imgs = el.find_all("img", recursive=False)
        for img in imgs:
            src = img.get("data-fullres-src") or img.get("data-src") or img.get("src")
            if src:
                data, ctype, fname = fetch_resource(src)
                if data:
                    upload_id = notion_upload_bytes(notion_token, fname, data, ctype)
                    if upload_id: blocks.append(image_block_from_upload(upload_id))
        for obj in el.find_all("object", recursive=False):
            data_url = obj.get("data") or obj.get("data-fullres-src")
            t = (obj.get("type") or "").lower() or None
            if data_url:
                data, ctype, fname = fetch_resource(data_url)
                if data:
                    upload_id = notion_upload_bytes(notion_token, fname, data, ctype or t)
                    if upload_id:
                        if ((t or ctype) or "").startswith("image/"): 
                            blocks.append(image_block_from_upload(upload_id))
                        else:
                            blocks.append(file_block_from_upload(upload_id))

    checkbox_unicode_true = ("☑","✅","✓","✔")
    checkbox_unicode_false = ("☐","⬜","☒","◻")

    body = soup.body or soup
    for el in body.descendants:
        if not isinstance(el, Tag): continue
        name = el.name.lower()

        if name in ("h1","h2","h3"):
            add_heading(int(name[1]), el)

        elif name == "blockquote":
            add_quote(el)

        elif name == "pre":
            code_el=el.find("code"); txt = code_el.get_text() if code_el else el.get_text()
            add_code(txt.strip())

        elif name in ("ul","ol"):
            ordered = (name=="ol")
            for li in el.find_all("li", recursive=False):
                handle_images(li)
                checked=False; is_todo=False
                cb = li.find("input", {"type":"checkbox"})
                if cb:
                    is_todo=True; checked = cb.has_attr("checked")
                if not is_todo and (li.get("data-tag") and "to-do" in li.get("data-tag","").lower()):
                    is_todo=True
                if not is_todo:
                    img = li.find("img")
                    if img and any(x in (img.get("alt","").lower()) for x in ["to do","todo","checked","unchecked"]):
                        is_todo=True; checked = "check" in img.get("alt","").lower()
                if not is_todo:
                    text = li.get_text(" ", strip=True)
                    if text.startswith(checkbox_unicode_true): is_todo=True; checked=True
                    elif text.startswith(checkbox_unicode_false): is_todo=True; checked=False
                    elif re.match(r"^\s*\[(x|X)\]\s+", text): is_todo=True; checked=True
                    elif re.match(r"^\s*\[\s\]\s+", text): is_todo=True; checked=False

                if is_todo:
                    add_todo(li, checked=checked)
                else:
                    t = "numbered_list_item" if ordered else "bulleted_list_item"
                    blocks.append({"object":"block","type":t,t:{"rich_text":build_rich_text(li)}})

        elif name == "p":
            handle_images(el)
            is_todo=False; checked=False
            if el.get("data-tag") and "to-do" in el.get("data-tag","").lower(): is_todo=True
            txt = el.get_text(" ", strip=True)
            if txt.startswith(checkbox_unicode_true): is_todo=True; checked=True
            elif txt.startswith(checkbox_unicode_false): is_todo=True; checked=False
            elif re.match(r"^\s*\[(x|X)\]\s+", txt): is_todo=True; checked=True
            elif re.match(r"^\s*\[\s\]\s+", txt): is_todo=True; checked=False

            if is_todo: add_todo(el, checked=checked)
            elif el.get_text(strip=True): add_paragraph_rich(el)

        elif name == "table":
            rows=[]
            for tr in el.find_all("tr", recursive=False):
                cells=[td.get_text(" ", strip=True) for td in tr.find_all(["td","th"], recursive=False)]
                rows.append(cells)
            if rows: tables.append(rows)

        elif name == "a":
            href=el.get("href","")
            if "/onenote/resources/" in href:
                data, ctype, fname = fetch_resource(href)
                if data:
                    upload_id = notion_upload_bytes(notion_token, fname, data, ctype)
                    if upload_id: blocks.append(file_block_from_upload(upload_id))

    if not blocks and soup.get_text(strip=True):
        blocks.append({"object":"block","type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":soup.get_text(' ', strip=True)}}]}})
    return blocks[:150], tables

def append_table(notion_token: str, parent_block_id: str, rows: List[List[str]]):
    table_block = {"object":"block","type":"table","table":{"table_width":max(len(r) for r in rows),"has_column_header":False,"has_row_header":False}}
    res = notion_append_children(notion_token, parent_block_id, [table_block])
    created = res.get("results", [])[-1]
    table_id = created.get("id")
    row_blocks = []
    for r in rows:
        cells = [[{"type":"text","text":{"content":c}}] for c in r]
        row_blocks.append({"object":"block","type":"table_row","table_row":{"cells":cells}})
    notion_append_children(notion_token, table_id, row_blocks)

# Main
def main():
    ap=argparse.ArgumentParser(description="OneNote -> Notion (v0.8.4 multipart fix)")
    ap.add_argument("--site-url", required=True)
    ap.add_argument("--notebook", help="Notebook name (fuzzy)")
    ap.add_argument("--notebook-id", help="Notebook id")
    ap.add_argument("--section", help="Section display name")
    ap.add_argument("--since")
    ap.add_argument("--database-id")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args=ap.parse_args()

    ms_client=os.getenv("MS_CLIENT_ID"); tenant=os.getenv("MS_TENANT_ID","consumers")
    notion_token=os.getenv("NOTION_TOKEN"); db_id=args.database_id or os.getenv("NOTION_DATABASE_ID")
    if not ms_client: print("ERROR: set MS_CLIENT_ID"); sys.exit(1)
    if not (notion_token and db_id): print("ERROR: set NOTION_TOKEN and NOTION_DATABASE_ID / --database-id"); sys.exit(1)

    app=ms_build_app(ms_client, tenant); ms_token=ms_acquire_token_device_code(app)["access_token"]
    site_id=resolve_site_id_from_url(ms_token, args.site_url)
    notebooks=list_site_notebooks(ms_token, site_id)

    nb=None
    if args.notebook_id:
        nb=next((n for n in notebooks if n.get("id")==args.notebook_id), None) or \
           next((n for n in notebooks if str(n.get("id","")).lower().endswith(str(args.notebook_id).lower().replace("1-",""))), None)
    if not nb and args.notebook:
        from difflib import get_close_matches
        name_map={n.get("displayName",""):n for n in notebooks}
        cand=get_close_matches(args.notebook, list(name_map.keys()), n=1, cutoff=0.2)
        if cand: nb=name_map[cand[0]]
    if not nb:
        print("Notebook not found. Available:");
        for n in notebooks: print(f" - {n.get('displayName')} [id={n.get('id')}]")
        sys.exit(2)
    if args.verbose: print(f"Selected notebook: {nb.get('displayName')} [id={nb.get('id')}]")

    sections=get_sections_from_notebook(ms_token, nb)
    if args.section:
        sec=next((s for s in sections if s.get("displayName")==args.section or s.get("displayName","").lower()==args.section.lower()), None)
        if not sec:
            print("Section not found. Available:"); [print(" -", s.get("displayName")) for s in sections]; sys.exit(3)
        sections=[sec]

    # state
    try:
        state = load_state()
    except Exception as e:
        print("[warn] load_state failed:", e); state={"pages":{}}

    for sec in sections:
        sec_name=sec.get("displayName")
        pages=list_pages_for_section(ms_token, sec, since=args.since, verbose=args.verbose)
        print(f"[{sec_name}] {len(pages)} page(s)")
        for p in pages:
            pid=p["id"]; title=p.get("title") or "Untitled"; web_url=p.get("links",{}).get("oneNoteWebUrl",{}).get("href")
            html=fetch_page_html(ms_token, site_id, pid)
            checksum=md5(html)
            st_key=f"{site_id}:{nb.get('id')}:{sec.get('id')}:{pid}"
            if args.resume and state["pages"].get(st_key,{}).get("checksum")==checksum:
                if args.verbose: print("  = skip unchanged:", title)
                continue

            if args.dry_run:
                print(f"[dry-run] would import '{title}' (media + tables + todos)")
                state["pages"][st_key]={"checksum":checksum,"notion_id":"dry-run","ts":int(time.time())}
                continue

            blocks, tables = html_to_blocks_and_tables(html, site_id, H_ms(ms_token), notion_token)

            # props
            db = notion_get_database(notion_token, db_id)
            props_def = db.get("properties",{})
            title_key = next((k for k,v in props_def.items() if v.get("type")=="title"), None)
            on_key = "OneNotePageId" if props_def.get("OneNotePageId",{}).get("type") in ("rich_text","url","title") else None
            on_type = props_def.get("OneNotePageId",{}).get("type") if on_key else None
            section_key = "Section" if props_def.get("Section",{}).get("type")=="select" else None
            src_key = "SourceURL" if props_def.get("SourceURL",{}).get("type")=="url" else None

            if not title_key: raise RuntimeError("Target Notion DB has no title property")
            props = { title_key: {"title":[{"type":"text","text":{"content":title[:200]}}]} }
            if on_key:
                if on_type=="rich_text": props[on_key]={"rich_text":[{"type":"text","text":{"content":pid}}]}
                elif on_type=="url": props[on_key]={"url": pid}
                elif on_type=="title": props[on_key]={"title":[{"type":"text","text":{"content":pid}}]}
            if section_key and sec_name: props[section_key]={"select":{"name":sec_name}}
            if src_key and web_url: props[src_key]={"url": web_url}

            page_id = None
            if on_key:
                page_id = notion_find_by_onenote_id(notion_token, db_id, on_key, on_type, pid)

            if page_id:
                notion_update_page(notion_token, page_id, props)
                notion_append_children(notion_token, page_id, blocks)
            else:
                page_id = notion_create_page(notion_token, db_id, props, blocks)

            for rows in tables:
                if rows: append_table(notion_token, page_id, rows)

            state["pages"][st_key]={"checksum":checksum,"notion_id":page_id,"ts":int(time.time())}
            save_state(state)
            print("  ✓", title)

    print("Done.")

if __name__=="__main__":
    main()
