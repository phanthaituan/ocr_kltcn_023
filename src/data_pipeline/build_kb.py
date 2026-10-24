#!/usr/bin/env python3
"""
build_kb.py - Bước 0.9: chuẩn hóa Knowledge Base (FoodOn + Open Food Facts) -> kb/foodon_off_merged.json

Đầu vào (có thể tự tải bằng --download):
  FoodOn          : foodon.owl                      (RDF/XML)
  OFF ingredients : taxonomies/food/ingredients.txt (định dạng taxonomy của OFF)
  OFF additives   : taxonomies/additives.txt

Đầu ra (trong --out_dir, mặc định kb/):
  foodon_off_merged.json : meta + entries (mỗi entry có aliases đã chuẩn hóa)
  kb_aliases.csv         : mỗi dòng 1 alias  -> dùng trực tiếp cho bước 1.4 (encode + FAISS)
  ins_to_kb.csv          : mã INS (từ bảng ADI của bạn) -> entry phụ gia của OFF
  vi_aliases_seed.csv    : (khi có --terms) top-N chuỗi ingredient tiếng Việt + gợi ý khớp KB, để bạn duyệt
  kb_report.md           : thống kê, kiểm tra, các điểm cần chú ý

Phạm vi:
  - FoodOn: các lớp KHÔNG deprecated, có nhãn, là con cháu của FOODON_00002403 ("food material", gồm cả "food product").
    Bỏ sinh vật (NCBITaxon), hóa chất không phải thực phẩm, địa danh... vì không phải đích liên kết của ingredient.
  - OFF: toàn bộ ingredients và additives; chỉ giữ tên tiếng Anh và tiếng Việt (--keep_langs).

Chuẩn hóa nhãn (theo bước 0.9): NFC, chữ thường, bỏ markup HTML, ký tự đặc biệt -> khoảng trắng, GIỮ dấu tiếng Việt.

Lưu ý: dùng xml.etree.iterparse (đọc theo luồng) thay cho owlready2/rdflib để không tốn RAM; kết quả giống nhau
(chỉ lấy label, synonym, định nghĩa, cha trực tiếp). off_tag là SUY RA từ tên đầu tiên (gần đúng, không lấy từ API).

Chạy:
  python build_kb.py --download kb/raw
  python build_kb.py --foodon kb/raw/foodon.owl --off_ingredients kb/raw/ingredients.txt \
         --off_additives kb/raw/additives.txt --adi_table ins_tables/adi_template.csv \
         --terms unique_terms.csv --out_dir kb [--vi_aliases kb/vi_aliases_manual.csv]
  python build_kb.py --selftest
"""
import argparse
import collections
import csv
import hashlib
import json
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

KB_BUILD_VERSION = "kb_v1"
FOODON_ROOT = "FOODON_00002403"           # food material
URLS = {
    "foodon.owl": "https://raw.githubusercontent.com/FoodOntology/foodon/master/foodon.owl",
    "ingredients.txt": "https://raw.githubusercontent.com/openfoodfacts/openfoodfacts-server/main/taxonomies/food/ingredients.txt",
    "additives.txt": "https://raw.githubusercontent.com/openfoodfacts/openfoodfacts-server/main/taxonomies/additives.txt",
}
OWL = "http://www.w3.org/2002/07/owl#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
OIO = "http://www.geneontology.org/formats/oboInOwl#"
OBO = "http://purl.obolibrary.org/obo/"
DEF_MAX = 400


# ----------------------------------------------------------------------------
# Chuẩn hóa
# ----------------------------------------------------------------------------
_TAG = re.compile(r"<[^>]+>")
_SPECIAL = re.compile(r"[^\w\s%]", re.UNICODE)
_PAREN = re.compile(r"\([^)]*\)")


def norm_label(s: str) -> str:
    """NFC, lowercase, bỏ markup, ký tự đặc biệt -> khoảng trắng (giữ chữ cái có dấu, chữ số, %)."""
    s = unicodedata.normalize("NFC", s or "")
    s = _TAG.sub(" ", s).lower().replace("_", " ")
    s = _SPECIAL.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def base_label(s: str) -> str:
    """Bỏ phần trong ngoặc: 'apple (raw)' -> 'apple'."""
    return norm_label(_PAREN.sub(" ", s or ""))


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d").replace("Đ", "D")


def off_slug(name: str) -> str:
    """Xấp xỉ cách OFF tạo tag: chữ thường, bỏ dấu của chữ Latin (giữ nguyên chữ Cyrillic/Hy Lạp/...),
    bỏ ký tự lạ, khoảng trắng -> '-'."""
    out = []
    for ch in unicodedata.normalize("NFC", name).lower():
        d = unicodedata.normalize("NFD", ch)
        if ch == "đ":
            out.append("d")
        elif d[0].isascii() and len(d) > 1:
            out.append(d[0])
        else:
            out.append(ch)
    s = re.sub(r"[^\w\s-]", "", "".join(out))
    s = re.sub(r"[\s_]+", "-", s.strip())
    return re.sub(r"-+", "-", s).strip("-")


# ----------------------------------------------------------------------------
# Tải dữ liệu
# ----------------------------------------------------------------------------
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    for name, url in URLS.items():
        out = dest / name
        print(f"Tải {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "build_kb/1.0"})
        with urllib.request.urlopen(req, timeout=300) as r, open(out, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        print(f"   -> {out} ({out.stat().st_size / 1e6:.1f} MB)")


# ----------------------------------------------------------------------------
# FoodOn
# ----------------------------------------------------------------------------
def _curie(uri):
    m = re.search(r"/obo/([A-Za-z]+_\d+)$", uri or "")
    return m.group(1) if m else None


def load_foodon(path: Path):
    classes, version = {}, None
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag == "{%s}versionIRI" % OWL:
            version = el.get("{%s}resource" % RDF)
        if el.tag != "{%s}Class" % OWL:
            continue
        cid = _curie(el.get("{%s}about" % RDF))
        if cid:
            d = {"label": None, "exact": [], "related": [], "narrow": [], "broad": [],
                 "def": None, "parents": [], "deprecated": False}
            for c in el:
                t, text = c.tag, (c.text or "").strip()
                if t == "{%s}label" % RDFS:
                    d["label"] = text
                elif t == "{%s}hasExactSynonym" % OIO:
                    d["exact"].append(text)
                elif t == "{%s}hasSynonym" % OIO:
                    d["related"].append(text)
                elif t == "{%s}hasNarrowSynonym" % OIO:
                    d["narrow"].append(text)
                elif t == "{%s}hasBroadSynonym" % OIO:
                    d["broad"].append(text)
                elif t == "{%s}IAO_0000115" % OBO:
                    d["def"] = text
                elif t == "{%s}subClassOf" % RDFS:
                    p = _curie(c.get("{%s}resource" % RDF))
                    if p:
                        d["parents"].append(p)
                elif t == "{%s}deprecated" % OWL and text == "true":
                    d["deprecated"] = True
            classes[cid] = d
        el.clear()
    return classes, version


def foodon_scope(classes, root=FOODON_ROOT):
    children = collections.defaultdict(list)
    for i, d in classes.items():
        for p in d["parents"]:
            children[p].append(i)
    seen, stack = {root}, [root]
    while stack:
        x = stack.pop()
        for c in children.get(x, []):
            if c not in seen:
                seen.add(c)
                stack.append(c)
    return {i for i in seen if i in classes and classes[i]["label"] and not classes[i]["deprecated"]}


# ----------------------------------------------------------------------------
# OFF taxonomy
# ----------------------------------------------------------------------------
_LANG_LINE = re.compile(r"^([a-z]{2,3}(?:_[A-Za-z]+)?):\s*(.*)$")
_PROP_LINE = re.compile(r"^([a-z_]+):([a-z]{2,3}):\s*(.*)$")
_PARENT = re.compile(r"^<\s*([a-z]{2,3}):\s*(.+)$")


def load_off(path: Path):
    """Trả về list entry: {tag, first_name, names{lang:[...]}, parents[tags], props{k:[v]}}."""
    entries, block = [], []

    def flush():
        if not block:
            return
        body = [l for l in block if not l.startswith("#")]
        if not body or body[0].startswith(("stopwords", "synonyms")):
            return
        e = {"names": {}, "parents": [], "props": {}, "tag": None, "first_name": None}
        for l in body:
            m = _PARENT.match(l)
            if m:
                e["parents"].append(f"{m.group(1)}:{off_slug(m.group(2))}")
                continue
            m = _LANG_LINE.match(l)
            if m:
                lang = m.group(1)
                names = [x.strip() for x in m.group(2).split(",") if x.strip()]
                e["names"].setdefault(lang, []).extend(names)
                if e["tag"] is None and names and lang != "xx":
                    e["first_name"] = names[0]
                    e["tag"] = f"{lang}:{off_slug(names[0])}"
                continue
            m = _PROP_LINE.match(l)
            if m:
                e["props"].setdefault(m.group(1), []).append(m.group(3).strip())
        if e["tag"]:
            entries.append(e)

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                flush()
                block = []
            else:
                block.append(line)
    flush()
    return merge_duplicate_tags(entries)


def merge_duplicate_tags(entries):
    """Nguồn OFF có mục trùng tên (khác cha). Cùng tag = cùng thực thể -> gộp tên, cha, thuộc tính."""
    merged, order = {}, []
    for e in entries:
        t = e["tag"]
        if t not in merged:
            merged[t] = e
            order.append(t)
            e["n_merged"] = 1
            continue
        m = merged[t]
        m["n_merged"] += 1
        for lang, names in e["names"].items():
            cur = m["names"].setdefault(lang, [])
            cur.extend(n for n in names if n not in cur)
        m["parents"].extend(p for p in e["parents"] if p not in m["parents"])
        for k, vals in e["props"].items():
            cur = m["props"].setdefault(k, [])
            cur.extend(v for v in vals if v not in cur)
    return [merged[t] for t in order]


# ----------------------------------------------------------------------------
# Dựng entry chung
# ----------------------------------------------------------------------------
def add_alias(entry, text, lang, kind, seen):
    n = norm_label(text)
    if len(n) < 2 or (n, lang) in seen:
        return
    seen.add((n, lang))
    entry["aliases"].append({"text": text.strip(), "norm": n, "lang": lang, "kind": kind})


def new_entry(kb_id, source, etype, label):
    return {"kb_id": kb_id, "source": source, "type": etype, "label": label, "aliases": [],
            "definition": None, "parents": [], "parents_unresolved": [], "is_leaf": True, "n_children": 0,
            "e_number": None, "ins_base": None, "additive_classes": [], "allergens": [], "xrefs": {},
            "xref_candidates": []}


def build_foodon_entries(classes, scope, keep_langs):
    out = []
    for cid in sorted(scope):
        d = classes[cid]
        e = new_entry(f"foodon:{cid}", "foodon", "food", d["label"])
        seen = set()
        add_alias(e, d["label"], "en", "label", seen)
        b = base_label(d["label"])
        if b and b != norm_label(d["label"]):
            add_alias(e, b, "en", "label_base", seen)
        for kind, key in (("exact", "exact"), ("related", "related"), ("narrow", "narrow"), ("broad", "broad")):
            for s in d[key]:
                add_alias(e, s, "en", kind, seen)
        e["definition"] = (d["def"] or "")[:DEF_MAX] or None
        e["parents"] = [f"foodon:{p}" for p in d["parents"] if p in scope]
        out.append(e)
    return out


def build_off_entries(raw, source, etype, keep_langs):
    out = []
    for r in raw:
        names = r["names"]
        lang0 = r["tag"].split(":")[0]
        label = r["first_name"]
        pre = "off_ing" if source == "off_ingredients" else "off_add"
        e = new_entry(f"{pre}:{r['tag']}", source, etype, label)
        e["off_tag"] = r["tag"]
        seen = set()
        for lang in keep_langs:
            for i, n in enumerate(names.get(lang, [])):
                add_alias(e, n, lang, "label" if (lang == lang0 and i == 0) else "synonym", seen)
        if not e["aliases"]:                                    # mục chỉ có tên ở ngôn ngữ khác
            for n in names.get(lang0, [])[:3]:
                add_alias(e, n, lang0, "label", seen)
        p = r["props"]
        e["definition"] = ((p.get("description") or [None])[0] or "")[:DEF_MAX] or None
        e["parents_unresolved"] = list(r["parents"])            # chuyển thành kb_id ở bước resolve
        e["allergens"] = [a.strip() for v in p.get("allergens", []) for a in v.split(",") if a.strip()]
        for k in ("wikidata", "ciqual_food_code", "usda_fdc_code"):
            if p.get(k):
                e["xrefs"][k] = p[k][0]
        if etype == "additive":
            en = (p.get("e_number") or [None])[0]
            if en:
                en = en.strip().lower()
            fn = (r["first_name"] or "").strip()
            m = re.match(r"^E\s*(\d{3,4}[a-z]?)", fn, re.I)
            code = en or (m.group(1).lower() if m else None)
            if code:
                e["ins_base"] = re.sub(r"[^0-9a-z]", "", code)
                e["e_number"] = "E" + e["ins_base"].upper()
                add_alias(e, e["e_number"], "xx", "code", seen)
                if m and fn.lower() != e["e_number"].lower():
                    add_alias(e, fn, "xx", "code", seen)       # vd 'E160a(i)'
            e["additive_classes"] = [c.strip() for v in p.get("additives_classes", []) for c in v.split(",") if c.strip()]
        out.append(e)
    return out


def resolve_parents(entries):
    """off_tag -> kb_id; chỉ giữ cha tìm được trong cùng taxonomy hoặc taxonomy phụ gia."""
    by_tag = {}
    for e in entries:
        if "off_tag" in e:
            by_tag.setdefault((e["source"], e["off_tag"]), e["kb_id"])
    for e in entries:
        if e["source"] == "foodon":
            continue
        res, unres = [], []
        for t in e["parents_unresolved"]:
            hit = by_tag.get((e["source"], t)) or by_tag.get(("off_additives", t))
            (res if hit else unres).append(hit or t)
        e["parents"], e["parents_unresolved"] = res, unres


def compute_leaves(entries):
    ids = {e["kb_id"] for e in entries}
    n = collections.Counter(p for e in entries for p in e["parents"] if p in ids)
    for e in entries:
        e["n_children"] = n.get(e["kb_id"], 0)
        e["is_leaf"] = e["n_children"] == 0


def link_exact(entries):
    """Ứng viên tương đương FoodOn <-> OFF ingredients theo tên tiếng Anh trùng khớp (CHƯA duyệt tay).
    match = loại alias phía FoodOn đã khớp: label | exact | label_base (nhãn bỏ phần trong ngoặc, độ tin cậy thấp hơn)."""
    idx = collections.defaultdict(dict)
    for e in entries:
        if e["source"] != "foodon":
            continue
        for a in e["aliases"]:
            if a["kind"] in ("label", "exact", "label_base") and len(a["norm"]) >= 3:
                idx[a["norm"]].setdefault(e["kb_id"], a["kind"])
    pairs = 0
    for e in entries:
        if e["source"] != "off_ingredients":
            continue
        hit = {}
        for a in e["aliases"]:
            if a["lang"] == "en":
                for k, kind in idx.get(a["norm"], {}).items():
                    prev = hit.get(k)
                    if prev is None or (prev == "label_base" and kind != "label_base"):
                        hit[k] = kind
        if hit and any(k != "label_base" for k in hit.values()):
            hit = {i: k for i, k in hit.items() if k != "label_base"}   # khớp yếu chỉ dùng khi không có khớp mạnh
        if hit:
            order = {"label": 0, "exact": 1, "label_base": 2}
            top = sorted(hit.items(), key=lambda kv: (order[kv[1]], kv[0]))[:3]
            e["xref_candidates"] = [{"kb_id": k, "match": f"en_{kind}_unreviewed"} for k, kind in top]
            pairs += 1
    return pairs


def apply_vi_aliases(entries, path):
    by_id = {e["kb_id"]: e for e in entries}
    added, bad = 0, []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            term, kid = (r.get("term_vi") or "").strip(), (r.get("kb_id") or "").strip()
            if not term or not kid:
                continue
            if "\ufffd" in term:
                bad.append((term, "ký tự lỗi U+FFFD"))
                continue
            e = by_id.get(kid)
            if not e:
                bad.append((term, f"kb_id không tồn tại: {kid}"))
                continue
            seen = {(a["norm"], a["lang"]) for a in e["aliases"]}
            before = len(e["aliases"])
            add_alias(e, term, "vi", "manual_vi", seen)
            added += len(e["aliases"]) - before
    return added, bad


# ----------------------------------------------------------------------------
# Ghi file và kiểm tra
# ----------------------------------------------------------------------------
MATCH_KINDS = {"label", "exact", "synonym", "manual_vi", "code"}   # bỏ label_base/related/narrow/broad (nhiễu)


def alias_index(entries, kinds=MATCH_KINDS):
    idx = collections.defaultdict(set)
    for e in entries:
        for a in e["aliases"]:
            if kinds is None or a["kind"] in kinds:
                idx[a["norm"]].add(e["kb_id"])
                idx[strip_accents(a["norm"])].add(e["kb_id"])
    return idx


def read_terms(path, term_type):
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("term_type") == term_type:
                rows.append((r["cleaned_term"].strip(), int(r["frequency"])))
    return sorted(rows, key=lambda x: -x[1])


def match_term(term, idx):
    for cand in (norm_label(term), base_label(term)):
        if cand and cand in idx:
            return cand, idx[cand]
    k = strip_accents(base_label(term))
    return (k, idx[k]) if k in idx else (None, set())


def write_outputs(out_dir, entries, meta, adi_table, terms_path, seed_top, report_extra):
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "foodon_off_merged.json", "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "entries": entries}, f, ensure_ascii=False, separators=(",", ":"))
    with open(out_dir / "kb_aliases.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["kb_id", "alias_norm", "alias_text", "lang", "kind", "source", "type", "is_leaf"])
        for e in entries:
            for a in e["aliases"]:
                w.writerow([e["kb_id"], a["norm"], a["text"], a["lang"], a["kind"], e["source"], e["type"], int(e["is_leaf"])])

    by_id = {e["kb_id"]: e for e in entries}
    adds = [e for e in entries if e["source"] == "off_additives" and e["ins_base"]]
    by_code = collections.defaultdict(list)
    for e in adds:
        by_code[e["ins_base"]].append(e)
    ins_rows, found_codes, total_codes = [], 0, 0
    if adi_table and Path(adi_table).exists():
        with open(adi_table, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                code = r["ins_code"].strip().lower()
                total_codes += 1
                hits = by_code.get(code, [])
                # ưu tiên entry có off_tag đúng bằng 'e'+code (không hậu tố La Mã)
                main = next((h for h in hits if h["off_tag"].split(":")[1] == "e" + code), hits[0] if hits else None)
                # biến thể La Mã của OFF: ins_base trùng code (vd e160a(i) có e_number 160a)
                found_codes += bool(hits)
                ins_rows.append([code, r.get("frequency", ""), main["kb_id"] if main else "",
                                 main["label"] if main else "", ";".join(h["kb_id"] for h in hits if h is not main),
                                 len(hits), int(bool(hits))])
        with open(out_dir / "ins_to_kb.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ins_code", "frequency", "kb_id_main", "kb_label_main", "kb_ids_variants", "n_entries", "found"])
            w.writerows(ins_rows)

    cov = {}
    if terms_path and Path(terms_path).exists():
        idx_all = alias_index(entries)
        idx_vi = alias_index([{**e, "aliases": [a for a in e["aliases"] if a["lang"] == "vi"]} for e in entries])
        ing = read_terms(terms_path, "ingredient")
        tot = sum(f for _, f in ing)
        for k in (50, 150, 300, len(ing)):
            sub = ing[:k]
            m_all = sum(f for t, f in sub if match_term(t, idx_all)[0])
            m_vi = sum(f for t, f in sub if match_term(t, idx_vi)[0])
            cov[k] = (m_all / tot, m_vi / tot, sum(1 for t, _ in sub if match_term(t, idx_all)[0]))
        with open(out_dir / "vi_aliases_seed.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["term_vi", "frequency", "auto_match_status", "candidates(kb_id|label)", "kb_id", "note"])
            pref = {"off_ingredients": 0, "off_additives": 1, "foodon": 2}
            for t, fq in ing[:seed_top]:
                key, ids = match_term(t, idx_all)
                if not ids:
                    w.writerow([t, fq, "no_match", "", "", ""])
                    continue
                cands = sorted(ids, key=lambda c: (pref[by_id[c]["source"]], c))
                srcs = collections.Counter(by_id[c]["source"] for c in cands)
                if len(cands) == 1:
                    status, pick = "unique", cands[0]
                elif max(srcs.values()) == 1:
                    status, pick = "multi_source", cands[0]        # cùng một khái niệm ở nhiều KB: chọn OFF trước
                else:
                    status, pick = f"ambiguous({len(cands)})", ""  # >1 entry trong cùng nguồn: bạn chọn
                w.writerow([t, fq, status, " ; ".join(f"{c}|{by_id[c]['label']}" for c in cands[:5]), pick, ""])

    # --- báo cáo
    src = collections.Counter(e["source"] for e in entries)
    n_alias = sum(len(e["aliases"]) for e in entries)
    n_vi = sum(1 for e in entries if any(a["lang"] == "vi" for a in e["aliases"]))
    coll = collections.defaultdict(set)
    for e in entries:
        for a in e["aliases"]:
            if a["kind"] in ("label", "exact", "synonym", "related", "narrow", "manual_vi"):
                coll[a["norm"]].add(e["kb_id"])
    amb = sum(1 for v in coll.values() if len(v) > 1)
    per_src = collections.defaultdict(lambda: collections.defaultdict(set))
    for e in entries:
        for a in e["aliases"]:
            if a["kind"] in ("label", "exact", "synonym", "related", "narrow", "manual_vi"):
                per_src[a["norm"]][e["source"]].add(e["kb_id"])
    amb_in = collections.Counter(sv for d in per_src.values() for sv, ids in d.items() if len(ids) > 1)
    amb_cross = sum(1 for d in per_src.values() if len(d) > 1)
    kinds = collections.Counter((a["lang"], a["kind"]) for e in entries for a in e["aliases"])
    xr = sum(1 for e in entries if e["xref_candidates"])
    lines = [f"# Báo cáo xây dựng KB ({KB_BUILD_VERSION})", "",
             f"- FoodOn: {meta['foodon_version']} | nguồn OFF: ingredients, additives (sha256 trong meta của JSON)",
             f"- Entry: **{len(entries)}** (FoodOn {src['foodon']}, OFF ingredients {src['off_ingredients']}, OFF additives {src['off_additives']})",
             f"- Alias: {n_alias} (trung bình {n_alias / max(len(entries), 1):.1f}/entry); entry có alias tiếng Việt: {n_vi} ({n_vi / len(entries):.1%})",
             f"- Entry lá (is_leaf): {sum(e['is_leaf'] for e in entries)}",
             f"- Alias trỏ tới >1 entry: {amb} (trong đó mơ hồ THẬT trong cùng một nguồn: {sum(amb_in.values())} "
             f"[FoodOn {amb_in['foodon']}, OFF ingredients {amb_in['off_ingredients']}, OFF additives {amb_in['off_additives']}]; "
             f"trùng giữa FoodOn và OFF, bình thường: {amb_cross})",
             f"- Ứng viên tương đương FoodOn↔OFF (trùng tên Anh, CHƯA duyệt): {xr} entry OFF ingredients",
             f"- Entry có nhóm dị nguyên (allergens): {sum(1 for e in entries if e['allergens'])}",
             f"- Entry phụ gia có E-number: {len(adds)}"]
    if total_codes:
        lines.append(f"- Mã INS của bạn có trong OFF additives: {found_codes}/{total_codes}")
    if cov:
        lines += ["", "## Độ phủ KB trên ingredient của bạn (so khớp CHUỖI sau chuẩn hóa; chưa có LLM/embedding)",
                  "| Nhóm chuỗi | Phủ lượt (KB đầy đủ) | Phủ lượt (chỉ alias tiếng Việt) | Số chuỗi khớp |", "|---|---|---|---|"]
        for k, (a, v, n) in cov.items():
            lines.append(f"| top {k} | {a:.1%} | {v:.1%} | {n} |")
    lines += ["", "## Số alias theo ngôn ngữ và loại", "| lang | kind | số alias |", "|---|---|---|"]
    lines += [f"| {l} | {k} | {n} |" for (l, k), n in sorted(kinds.items(), key=lambda x: -x[1])]
    lines += ["", "## Cách dùng cho bước 1.4 (encode + FAISS)",
              "- Đọc `kb_aliases.csv`; mỗi dòng là một alias. Khuyến nghị encode các loại: `label`, `exact`, `synonym`, `manual_vi`, `code`.",
              "- Các loại `related`, `narrow`, `broad`, `label_base` của FoodOn nhiễu hơn: để dạng tùy chọn, thử bật/tắt bằng dev set.",
              "- Sau khi lấy top-k alias gần nhất, gộp về `kb_id` (nhiều alias cùng một entry); dùng `is_leaf`, `parents`, `definition` cho bước re-rank LLM.",
              "- `lang = xx` là mã E-number; chỉ dùng khi chuỗi truy vấn là mã. Chuỗi có mã INS nên tra trực tiếp qua `ins_to_kb.csv`, không cần embedding.",
              "", "## Giới hạn cần biết",
              "- `off_tag` suy ra từ tên đầu tiên, gần đúng; hãy đối chiếu với API/taxonomy gốc trước khi dùng làm nhãn gold.",
              "- `xref_candidates` (FoodOn↔OFF) chỉ là trùng tên tiếng Anh, CHƯA duyệt tay.",
              "- OFF chỉ có tên tiếng Việt cho một phần nhỏ entry; độ phủ tiếng Việt chủ yếu đến từ alias thủ công (`--vi_aliases`).",
              "- Phạm vi FoodOn chỉ gồm nhánh `food material`; sinh vật, nước (CHEBI:15377) và muối (CHEBI:24866) nằm ngoài nhánh này, đã được OFF bù (en:water, en:salt).",
              "- Độ phủ đo ở trên là so khớp CHUỖI; chưa phản ánh chất lượng truy hồi bằng embedding đa ngôn ngữ."]
    lines += report_extra
    (out_dir / "kb_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"entries": len(entries), "aliases": n_alias, "ins_found": (found_codes, total_codes), "cov": cov,
            "ambiguous_aliases": amb, "xref": xr}


# ----------------------------------------------------------------------------
# Selftest
# ----------------------------------------------------------------------------
def selftest():
    fails = 0

    def check(name, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print("OK  " if ok else "FAIL", name, "" if ok else f"\n   got={got!r}\n   want={want!r}")

    check("norm: hoa/thường + NFC", norm_label("Muối  I-ỐT"), "muối i ốt")
    check("norm: NFD -> NFC", norm_label(unicodedata.normalize("NFD", "Đường")), "đường")
    check("norm: markup", norm_label("<b>Sugar</b> (raw)"), "sugar raw")
    check("norm: ký tự đặc biệt", norm_label("E160a(i)"), "e160a i")
    check("base_label", base_label("apple (raw)"), "apple")
    check("slug additive", off_slug("E160a(i)"), "e160ai")
    check("slug ingredient", off_slug("Sunflower oil"), "sunflower-oil")
    check("slug có dấu", off_slug("Dầu hướng dương"), "dau-huong-duong")
    check("slug Cyrillic không bị xóa", off_slug("пшеничен декстрин"), "пшеничен-декстрин")
    check("slug không rỗng với chữ lạ", off_slug("Ё-мёд") != "", True)
    check("strip_accents đ", strip_accents("đường"), "duong")
    # parser OFF trên khối giả
    import tempfile, os
    txt = ("stopwords:en: a, the\n\n< en: E160a\nen: E160a(i), Beta-carotene, b-carotene\nxx: E160a(i)\nvi: E160a(i), Beta-caroten\n"
           "additives_classes:en: en:colour\ne_number:en: 160a\nwikidata:en: Q1\n\n"
           "< en: gelatin\nen: fish gelatine\nvi: gelatin cá\nallergens:en: en:fish\nciqual_food_code:en: 123\n\n"
           "fr: sel\nen: salt\n")
    p = Path(tempfile.mkdtemp()) / "t.txt"
    p.write_text(txt, encoding="utf-8")
    raw = load_off(p)
    check("OFF: số mục (bỏ stopwords)", len(raw), 3)
    check("OFF: tag E160a(i)", raw[0]["tag"], "en:e160ai")
    check("OFF: cha", raw[0]["parents"], ["en:e160a"])
    check("OFF: tag mục bắt đầu bằng fr", raw[2]["tag"], "fr:sel")
    dup = load_off(_w("< en: a\nen: Little millet\nla: Panicum\n\n< en: b\nen: little millet\nhr: proso\nallergens:en: en:x\n"))
    check("OFF: gộp mục trùng tag", (len(dup), sorted(dup[0]["parents"]), sorted(dup[0]["names"]), dup[0]["n_merged"], dup[0]["props"].get("allergens")), (1, ["en:a", "en:b"], ["en", "hr", "la"], 2, ["en:x"]))
    add = build_off_entries([raw[0]], "off_additives", "additive", ("en", "vi"))[0]
    check("additive: ins_base", add["ins_base"], "160a")
    check("additive: e_number", add["e_number"], "E160A")
    check("additive: nhóm", add["additive_classes"], ["en:colour"])
    check("additive: có alias vi", any(a["lang"] == "vi" for a in add["aliases"]), True)
    ing = build_off_entries([raw[1]], "off_ingredients", "ingredient", ("en", "vi"))[0]
    check("ingredient: dị nguyên", ing["allergens"], ["en:fish"])
    check("ingredient: xref", ing["xrefs"], {"ciqual_food_code": "123"})
    check("ingredient: kb_id", ing["kb_id"], "off_ing:en:fish-gelatine")
    fr = build_off_entries([raw[2]], "off_ingredients", "ingredient", ("vi",))[0]
    check("mục không có tên en/vi vẫn có alias", len(fr["aliases"]) >= 1, True)
    # parents + lá
    a = new_entry("off_ing:en:x", "off_ingredients", "ingredient", "x"); a["off_tag"] = "en:x"
    b = new_entry("off_ing:en:y", "off_ingredients", "ingredient", "y"); b["off_tag"] = "en:y"; b["parents_unresolved"] = ["en:x", "en:zzz"]
    resolve_parents([a, b]); compute_leaves([a, b])
    check("resolve cha", (b["parents"], b["parents_unresolved"]), (["off_ing:en:x"], ["en:zzz"]))
    check("is_leaf", (a["is_leaf"], b["is_leaf"]), (False, True))
    # FoodOn scope trên OWL giả
    owl = ('<?xml version="1.0"?><rdf:RDF xmlns:rdf="%s" xmlns:owl="%s" xmlns:rdfs="%s" xmlns:oboInOwl="%s">'
           '<owl:Ontology rdf:about="x"><owl:versionIRI rdf:resource="http://purl.obolibrary.org/obo/foodon/releases/2026-01-01/foodon.owl"/></owl:Ontology>'
           '<owl:Class rdf:about="%sFOODON_00002403"><rdfs:label xml:lang="en">food material</rdfs:label></owl:Class>'
           '<owl:Class rdf:about="%sFOODON_1"><rdfs:subClassOf rdf:resource="%sFOODON_00002403"/><rdfs:label xml:lang="en">sugar (raw)</rdfs:label>'
           '<oboInOwl:hasExactSynonym>sucrose</oboInOwl:hasExactSynonym><oboInOwl:hasBroadSynonym>sweetener</oboInOwl:hasBroadSynonym></owl:Class>'
           '<owl:Class rdf:about="%sFOODON_2"><rdfs:subClassOf rdf:resource="%sFOODON_00002403"/><rdfs:label>old</rdfs:label><owl:deprecated>true</owl:deprecated></owl:Class>'
           '<owl:Class rdf:about="%sNCBITaxon_9"><rdfs:label>wheat plant</rdfs:label></owl:Class>'
           '</rdf:RDF>') % (RDF, OWL, RDFS, OIO, OBO, OBO, OBO, OBO, OBO, OBO)
    q = Path(tempfile.mkdtemp()) / "f.owl"
    q.write_text(owl, encoding="utf-8")
    cls, ver = load_foodon(q)
    sc = foodon_scope(cls)
    check("FoodOn: phiên bản", ver.split("/")[-2], "2026-01-01")
    check("FoodOn: scope (bỏ deprecated, bỏ ngoài nhánh)", sorted(sc), ["FOODON_00002403", "FOODON_1"])
    fe = {e["kb_id"]: e for e in build_foodon_entries(cls, sc, ("en",))}
    check("FoodOn: alias base + exact", sorted(a["norm"] for a in fe["foodon:FOODON_1"]["aliases"]), ["sucrose", "sugar", "sugar raw", "sweetener"])
    check("FoodOn: cha trong scope", fe["foodon:FOODON_1"]["parents"], ["foodon:FOODON_00002403"])
    # liên kết chéo
    off = build_off_entries(load_off(_w("en: sugar\nvi: đường\n")), "off_ingredients", "ingredient", ("en", "vi"))
    allx = list(fe.values()) + off
    check("link_exact", link_exact(allx), 1)
    check("link_exact nội dung", (off[0]["xref_candidates"][0]["kb_id"], off[0]["xref_candidates"][0]["match"]), ("foodon:FOODON_1", "en_label_base_unreviewed"))
    print("KẾT QUẢ:", "TẤT CẢ ĐẠT" if not fails else f"{fails} CA LỖI")
    return fails


def _w(text):
    import tempfile
    p = Path(tempfile.mkdtemp()) / "x.txt"
    p.write_text(text, encoding="utf-8")
    return p


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--download", type=Path, help="tải 3 file nguồn vào thư mục này rồi thoát")
    ap.add_argument("--foodon", type=Path)
    ap.add_argument("--off_ingredients", type=Path)
    ap.add_argument("--off_additives", type=Path)
    ap.add_argument("--adi_table", type=Path, help="adi_template.csv (để tạo ins_to_kb.csv)")
    ap.add_argument("--terms", type=Path, help="unique_terms.csv (để đo độ phủ và tạo vi_aliases_seed.csv)")
    ap.add_argument("--seed_top", type=int, default=150)
    ap.add_argument("--vi_aliases", type=Path, help="CSV term_vi,kb_id do bạn duyệt tay (gộp vào alias tiếng Việt)")
    ap.add_argument("--keep_langs", default="en,vi")
    ap.add_argument("--out_dir", type=Path, default=Path("kb"))
    a = ap.parse_args()
    if a.selftest:
        sys.exit(1 if selftest() else 0)
    if a.download:
        download(a.download)
        return
    for need in ("foodon", "off_ingredients", "off_additives"):
        if not getattr(a, need):
            ap.error(f"cần --{need} (hoặc dùng --download trước)")
    langs = tuple(x.strip() for x in a.keep_langs.split(",") if x.strip())

    print("Đọc FoodOn (theo luồng, có thể mất 1-2 phút)...")
    classes, version = load_foodon(a.foodon)
    scope = foodon_scope(classes)
    print(f"  lớp có ID: {len(classes)} | trong phạm vi (food material, không deprecated): {len(scope)}")
    entries = build_foodon_entries(classes, scope, langs)
    print("Đọc OFF taxonomy...")
    ing_raw, add_raw = load_off(a.off_ingredients), load_off(a.off_additives)
    entries += build_off_entries(ing_raw, "off_ingredients", "ingredient", langs)
    entries += build_off_entries(add_raw, "off_additives", "additive", langs)
    resolve_parents(entries)
    compute_leaves(entries) 
    n_x = link_exact(entries)
    extra = []
    if a.vi_aliases:
        added, bad = apply_vi_aliases(entries, a.vi_aliases)
        print(f"Alias tiếng Việt thủ công: +{added}; lỗi: {len(bad)}")
        extra = ["", f"## Alias tiếng Việt thủ công: +{added} alias; {len(bad)} dòng bị từ chối"] + [f"- {t}: {why}" for t, why in bad[:20]]
    ids = [e["kb_id"] for e in entries]
    assert len(ids) == len(set(ids)), "kb_id bị trùng"
    meta = {"kb_build_version": KB_BUILD_VERSION, "foodon_version": (version or "").split("/")[-2] if version else None,
            "foodon_scope_root": FOODON_ROOT, "keep_langs": list(langs),
            "sources": {n: {"file": str(p), "sha256": sha256(p), "bytes": p.stat().st_size}
                        for n, p in (("foodon", a.foodon), ("off_ingredients", a.off_ingredients), ("off_additives", a.off_additives))},
            "normalization": "NFC + lowercase + strip HTML + non-word chars -> space (giữ dấu tiếng Việt, %, chữ số)",
            "notes": ["off_tag suy ra từ tên đầu tiên (gần đúng)", "xref_candidates chưa duyệt tay"]}
    stats = write_outputs(a.out_dir, entries, meta, a.adi_table, a.terms, a.seed_top, extra)
    print(json.dumps({k: (v if k != "cov" else {str(kk): [round(x, 3) if isinstance(x, float) else x for x in vv] for kk, vv in v.items()}) for k, v in stats.items()}, ensure_ascii=False, indent=1))
    print(f"Đã ghi vào {a.out_dir}/")


if __name__ == "__main__":
    main()