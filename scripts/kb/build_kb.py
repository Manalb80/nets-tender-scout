"""Build the NETS proposal knowledge base: PDF -> headed paragraph chunks -> JSON.
Usage: python3 -I build_kb.py <pdf_dir> <out_dir>
Each chunk: {id, source, client, section, text, words, terms:[top keywords]}.
"""
import sys, os, re, json, collections, hashlib
import fitz  # PyMuPDF

pdf_dir, out_dir = sys.argv[1], sys.argv[2]
scorer_dir = sys.argv[3] if len(sys.argv)>3 else None
score_tender=None
if scorer_dir:
    sys.path.insert(0, scorer_dir)
    from scorer import score_tender, SOLUTIONS as _SOLS
    NAME_OF={x["id"]:x["name"] for x in _SOLS}
os.makedirs(out_dir, exist_ok=True)

STOP=set("""a an the and or of to in for on with by from as at is are was were be been this that these those it its into over under
than then also any all per each our we us you your their they them he she his her will shall may can must should would could
not no nor but if so such via etc which who whom whose where when while within without between among about above below
nets international proposal technical section page table figure""".split())

HEAD_RE=re.compile(r'^\s*((\d+(\.\d+)*)[\.\)]?\s+)?([A-Z][A-Za-z0-9 &/,\-\(\)]{3,80})\s*$')

def clean(s):
    s=s.replace(' ',' ')
    s=re.sub(r'[ \t]+',' ',s)
    s=re.sub(r'\n{3,}','\n\n',s)
    return s.strip()

def client_of(name):
    n=name.replace('.pdf','')
    m=re.match(r'(?i)^technical proposal \(([^)]*)\) for\s*(.+)$',n)
    if m: return (m.group(2).replace('Statelife','State Life')+' ('+m.group(1)+')').strip()
    n=re.sub(r'(?i)nets[-_ ]*','',n)
    n=re.sub(r'(?i)[-_ ]*(technical|tech)[-_ ]*(proposal|prposal).*$','',n)
    n=re.sub(r'\(\d\)','',n).replace('-',' ').replace('_',' ')
    n=re.sub(r'(?i)^technical proposal \(([^)]*)\) for\s*','',n)+(' ('+re.search(r'\(([^)]*)\)',name).group(1)+')' if re.search(r'(?i)^technical proposal \(',name) else '')
    n=n.replace('Statelife','State Life')
    return re.sub(r'\s+',' ',n).strip() or name

def is_heading(line):
    if len(line)>90 or len(line)<4: return False
    if line.endswith(('.',',',';',':')) and not re.match(r'^\d',line): return False
    m=HEAD_RE.match(line)
    if not m: return False
    words=line.split()
    caps=sum(1 for w in words if w[:1].isupper() or w.isdigit())
    return caps/len(words)>=0.6

def terms_of(text,k=12):
    ws=re.findall(r'[a-z][a-z0-9\-\+\.]{2,}',text.lower())
    ws=[w.strip('.') for w in ws if w not in STOP and not w.isdigit()]
    c=collections.Counter(ws)
    return [w for w,_ in c.most_common(k)]

chunks=[];files=[]
for fn in sorted(os.listdir(pdf_dir)):
    if not fn.lower().endswith('.pdf'): continue
    path=os.path.join(pdf_dir,fn)
    try:
        doc=fitz.open(path)
    except Exception as e:
        files.append({"file":fn,"error":str(e)});continue
    client=client_of(fn)
    section="Introduction";buf=[];nchunks=0;pages=doc.page_count;chars=0
    def flush():
        global buf,nchunks
        txt=clean('\n'.join(buf));buf=[]
        if len(txt.split())<25: return
        if re.search(r'(?i)contact person|^contents$|table of contents|^urdu$|^modes of communication',section): return
        # split long sections into ~220-word windows at paragraph boundaries
        paras=[p for p in re.split(r'\n\s*\n',txt) if p.strip()]
        cur=[];cw=0
        def emit(ps):
            global nchunks
            t=clean('\n\n'.join(ps))
            if len(t.split())<25: return
            cid=hashlib.md5((fn+section+t[:80]).encode()).hexdigest()[:12]
            chunks.append({"id":cid,"source":fn,"client":client,"section":section[:80],"text":t[:2400],"words":len(t.split()),"terms":terms_of(t)})
            nchunks+=1
        for p in paras:
            w=len(p.split())
            if cw+w>260 and cur: emit(cur);cur=[];cw=0
            cur.append(p);cw+=w
        if cur: emit(cur)
    for pno in range(pages):
        text=doc[pno].get_text("text")
        chars+=len(text)
        for line in text.split('\n'):
            l=line.strip()
            if not l: buf.append('');continue
            if is_heading(l) and len(buf)>3:
                flush();section=re.sub(r'^\d+(\.\d+)*[\.\)]?\s+','',l)
            else:
                buf.append(l)
    flush()
    files.append({"file":fn,"client":client,"pages":pages,"chars":chars,"chunks":nchunks,"scanned":chars<500*max(1,pages)})
# Vertical tags: run the NETS scorer over each file's full text and keep the solution ids it matches.
if score_tender:
    by_file={}
    for c in chunks: by_file.setdefault(c["source"],[]).append(c["text"])
    vert_of={}
    for fn,texts in by_file.items():
        full=(client_of(fn)+" . "+" ".join(texts))[:60000]
        low=full.lower()
        counts={}
        for sol in _SOLS:
            n=0
            for k in sol["keywords"]:
                if len(k)<4: continue
                n+=len(re.findall(r'(?<![a-z0-9])'+re.escape(k.lower())+r'(?![a-z0-9])',low))
            counts[sol["id"]]=n
        # a vertical counts when its keywords occur at least 6 times in the proposal; keep the top 3
        top=[k for k,v in sorted(counts.items(),key=lambda x:-x[1]) if v>=6][:3]
        vert_of[fn]=top
    for c in chunks: c["verticals"]=vert_of.get(c["source"],[])
    for f in files: f["verticals"]=vert_of.get(f.get("file"),[]); f["vertical_names"]=[NAME_OF.get(v,v) for v in f["verticals"]]
json.dump(chunks,open(os.path.join(out_dir,'kb_chunks.json'),'w'),ensure_ascii=False)
json.dump(files,open(os.path.join(out_dir,'kb_files.json'),'w'),indent=1)
print(len(files),"files",len(chunks),"chunks",sum(c['words'] for c in chunks),"words")
for f in files: print(f.get('client','?'),'|',f.get('pages'),'pages',f.get('chunks'),'chunks', 'SCANNED' if f.get('scanned') else '')
