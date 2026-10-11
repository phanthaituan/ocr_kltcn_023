"""
ocr_benchmark.py
So sánh các engine OCR trên tập benchmark, chấm bằng ĐỘ PHỦ chuỗi gold
(vì gold của ViFoodLabel nhóm theo field, không có chuỗi chữ theo thứ tự đọc nên không tính CER/WER chuẩn).

Engine hỗ trợ:
  easyocr           : EasyOCR đủ bộ (detect + recognize), ngôn ngữ vi+en
  easyocr_vietocr   : EasyOCR detect (CRAFT) + VietOCR recognize
  selftest_perfect / selftest_noisy : chạy thử luồng chấm điểm, KHÔNG dùng OCR thật

Ví dụ:
  python ocr_benchmark.py --ids benchmark_ids.txt --images_dir data/raw/images \
      --gold_dir data/annotations/gold_parsed --engines easyocr easyocr_vietocr --limit 3
"""
import argparse, csv, json, random, re, sys, time, unicodedata
from pathlib import Path

# Thêm thư mục gốc vào sys.path để import được src.common
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common import paths

IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None

# ---------- chuẩn hóa & trích mã INS ----------
CODE_RE = re.compile(r"(?<![\d,.])(\d{3,4})([a-z])?(?:\s*\(\s*(iv|v|i{1,3})\s*\))?(?![\d])", re.I)


def extract_ins(text):
    out = set()
    for m in CODE_RE.finditer(text):
        num, letter = m.group(1), (m.group(2) or "").lower()
        if 100 <= int(num) <= 1599:
            out.add(num + letter)
    return out


def norm_text(t):
    t = unicodedata.normalize("NFC", t).lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def strip_diac(t):
    t = unicodedata.normalize("NFD", t.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def clean_item(s):
    s = unicodedata.normalize("NFC", s).lower()
    prev = None
    while prev != s:                       # bỏ nội dung trong ngoặc (kể cả ngoặc lồng)
        prev = s
        s = re.sub(r"\([^()]*\)", " ", s)
    s = re.sub(r"\d+([.,]\d+)?\s*%", " ", s)
    return norm_text(s)


def coverage(items, ocr_norm, ocr_nodiac, thr):
    n = ex = nd = fz = 0
    for it in items:
        c = clean_item(it)
        if len(c) < 3:
            continue
        n += 1
        cn = strip_diac(c)
        e = c in ocr_norm
        d = cn in ocr_nodiac
        f = d or (fuzz is not None and fuzz.partial_ratio(cn, ocr_nodiac) >= thr)
        ex += e; nd += d; fz += f
    return n, ex, nd, fz


# ---------- ghép ô chữ thành dòng ----------
def lines_from_boxes(items):
    """items: (x1, y1, x2, y2, text) -> chuỗi nhiều dòng theo thứ tự trên-xuống, trái-phải."""
    items = [b for b in items if b[4] and b[4].strip()]
    if not items:
        return ""
    hs = sorted(b[3] - b[1] for b in items)
    med = hs[len(hs) // 2] or 1
    items = sorted(items, key=lambda b: (b[1] + b[3]) / 2)
    lines, cur = [], [items[0]]
    cur_y = (items[0][1] + items[0][3]) / 2
    for b in items[1:]:
        yc = (b[1] + b[3]) / 2
        if abs(yc - cur_y) <= 0.6 * med:
            cur.append(b)
            cur_y = sum((x[1] + x[3]) / 2 for x in cur) / len(cur)
        else:
            lines.append(cur); cur = [b]; cur_y = yc
    lines.append(cur)
    return "\n".join(" ".join(x[4] for x in sorted(l, key=lambda b: b[0])) for l in lines)


# ---------- engine ----------
class Ctx:
    def __init__(self, args):
        self.args = args
        self._easy = None
        self._viet = {}

    def easy_reader(self):
        if self._easy is None:
            import easyocr
            self._easy = easyocr.Reader(["vi", "en"], gpu=not self.args.cpu)
        return self._easy

    def vietocr(self, name):
        if name not in self._viet:
            from vietocr.tool.predictor import Predictor
            from vietocr.tool.config import Cfg
            cfg = Cfg.load_config_from_name(name)
            cfg["cnn"]["pretrained"] = False
            cfg["device"] = "cpu" if self.args.cpu else "cuda:0"
            cfg["predictor"]["beamsearch"] = False
            self._viet[name] = Predictor(cfg)
        return self._viet[name]


def make_easyocr(ctx):
    reader = ctx.easy_reader()

    def run(path):
        res = reader.readtext(str(path), detail=1, paragraph=False)
        items = [(min(p[0] for p in b), min(p[1] for p in b),
                  max(p[0] for p in b), max(p[1] for p in b), t) for b, t, _ in res]
        return lines_from_boxes(items)
    return run


def make_easyocr_vietocr(ctx):
    import numpy as np
    from PIL import Image
    reader = ctx.easy_reader()
    pred = ctx.vietocr(ctx.args.vietocr_model)

    def run(path):
        img = Image.open(path).convert("RGB")
        horizontal, free = reader.detect(np.array(img))
        boxes = [(x1, y1, x2, y2) for x1, x2, y1, y2 in horizontal[0]]
        for poly in free[0]:
            xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
        crops, meta = [], []
        for x1, y1, x2, y2 in boxes:
            x1, y1 = max(int(x1), 0), max(int(y1), 0)
            x2, y2 = min(int(x2), img.width), min(int(y2), img.height)
            if x2 - x1 < 8 or y2 - y1 < 8:
                continue
            crops.append(img.crop((x1, y1, x2, y2))); meta.append((x1, y1, x2, y2))
        texts = []
        for i in range(0, len(crops), 16):
            chunk = crops[i:i + 16]
            try:
                texts += pred.predict_batch(chunk)
            except AttributeError:
                texts += [pred.predict(c) for c in chunk]
        return lines_from_boxes([(*m, t) for m, t in zip(meta, texts)])
    return run


def make_selftest(ctx, noisy):
    gold_dir = Path(ctx.args.gold_dir)
    rng = random.Random(0)

    def run(path):
        g = json.load(open(gold_dir / f"{Path(path).stem}.json", encoding="utf-8"))
        text = "\n".join(g.get("gold_additives_raw", []) + g.get("gold_ingredients_raw", [])
                         + g.get("gold_warning_raw", []))
        if noisy:
            text = strip_diac(text)
            text = re.sub(r"\d", lambda m: m.group(0) if rng.random() > 0.3 else "", text)
        return text
    return run


# def make_paddleocr(ctx):
#     import logging
#     logging.getLogger('ppocr').setLevel(logging.ERROR)
#     from paddleocr import PaddleOCR
#     ocr = PaddleOCR(use_textline_orientation=True, lang='vi', device='cpu' if ctx.args.cpu else 'gpu')
    
#     def run(path):
#         result = ocr.ocr(str(path), cls=True)
#         if not result or not result[0]:
#             return ""
#         items = []
#         for line in result[0]:
#             box, (text, score) = line
#             xs = [p[0] for p in box]
#             ys = [p[1] for p in box]
#             items.append((min(xs), min(ys), max(xs), max(ys), text))
#         return lines_from_boxes(items)
#     return run

def make_paddleocr(ctx):
    from paddleocr import PaddleOCR
    ocr = PaddleOCR(lang="vi", use_textline_orientation=True,
                    use_doc_orientation_classify=False, use_doc_unwarping=False,
                    device="cpu" if ctx.args.cpu else "gpu")

    def run(path):
        items = []
        for r in ocr.predict(str(path)):
            for poly, text in zip(r["rec_polys"], r["rec_texts"]):
                xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
                items.append((min(xs), min(ys), max(xs), max(ys), text))
        return lines_from_boxes(items)
    return run


def make_doctr(ctx):
    from doctr.models import ocr_predictor
    from doctr.io import DocumentFile
    predictor = ocr_predictor(pretrained=True)
    if not ctx.args.cpu:
        try:
            predictor.cuda()
        except Exception:
            pass
            
    def run(path):
        doc = DocumentFile.from_images(str(path))
        result = predictor(doc)
        items = []
        page = result.pages[0]
        h, w = page.dimensions
        for block in page.blocks:
            for line in block.lines:
                for word in line.words:
                    geom = word.geometry
                    x1, y1 = geom[0][0] * w, geom[0][1] * h
                    x2, y2 = geom[1][0] * w, geom[1][1] * h
                    items.append((x1, y1, x2, y2, word.value))
        return lines_from_boxes(items)
    return run


ENGINES = {
    "easyocr": make_easyocr,
    "easyocr_vietocr": make_easyocr_vietocr,
    "paddleocr": make_paddleocr,
    "doctr": make_doctr,
    "selftest_perfect": lambda c: make_selftest(c, False),
    "selftest_noisy": lambda c: make_selftest(c, True),
}


# ---------- tiện ích ----------
def find_image(images_dir, img_id):
    for ext in IMG_EXTS:
        for e in (ext, ext.upper()):
            p = images_dir / f"{img_id}{e}"
            if p.exists():
                return p
    hits = sorted(images_dir.glob(f"{img_id}.*"))
    return hits[0] if hits else None


def peak_vram_mb():
    try:
        import torch
        if torch.cuda.is_available():
            return round(torch.cuda.max_memory_allocated() / 2**20)
    except ImportError:
        pass
    return None


def reset_vram_peak():
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except ImportError:
        pass


def pct(a, b):
    return round(100 * a / b, 1) if b else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True, help="File txt chứa list ID (ví dụ: benchmark_ids.txt)")
    ap.add_argument("--images_dir", default=str(paths.RAW_IMAGES_DIR))
    ap.add_argument("--gold_dir", default=str(paths.GOLD_PARSED_DIR))
    ap.add_argument("--engines", nargs="+", required=True, choices=list(ENGINES))
    ap.add_argument("--out_dir", default=str(paths.RESULTS_DIR / "ocr_benchmark"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--force", action="store_true", help="chạy lại OCR dù đã có kết quả lưu")
    ap.add_argument("--score_only", action="store_true", help="chỉ chấm điểm từ kết quả đã lưu")
    ap.add_argument("--vietocr_model", default="vgg_transformer")
    ap.add_argument("--fuzzy_threshold", type=int, default=88)
    ap.add_argument("--margin", type=float, default=3.0, help="chênh lệch INS recall (điểm %) để coi là hơn hẳn")
    ap.add_argument("--max_vram_mb", type=int, default=0)
    ap.add_argument("--max_sec", type=float, default=0)
    args = ap.parse_args()

    ids = [l.strip() for l in open(args.ids, encoding="utf-8") if l.strip()]
    if args.limit:
        ids = ids[:args.limit]
    images_dir, gold_dir, out_dir = Path(args.images_dir), Path(args.gold_dir), Path(args.out_dir)
    ctx = Ctx(args)
    if fuzz is None:
        print("[!] Chưa cài rapidfuzz (pip install rapidfuzz): cột *_fuzzy sẽ bằng *_nodiac.")

    gold = {}
    for i in ids:
        gp = gold_dir / f"{i}.json"
        if not gp.exists():
            print(f"[!] thiếu gold {gp}, bỏ qua ID {i}")
            continue
        gold[i] = json.load(open(gp, encoding="utf-8"))
    ids = list(gold)

    per_image, summaries = [], []
    for eng in args.engines:
        edir = out_dir / eng
        edir.mkdir(parents=True, exist_ok=True)
        meta_path = edir / "meta.json"
        todo = [i for i in ids if args.force or not (edir / f"{i}.json").exists()]
        if todo and not args.score_only:
            reset_vram_peak()
            run = ENGINES[eng](ctx)
            first = find_image(images_dir, todo[0])
            if first:
                try:
                    run(first)                      # chạy khởi động, không tính giờ
                except Exception as e:
                    print(f"[{eng}] lỗi khi khởi động: {e}")
            for n, i in enumerate(todo, 1):
                p = find_image(images_dir, i)
                rec = {"id": i, "text": "", "seconds": None, "error": None}
                if p is None:
                    rec["error"] = "không tìm thấy ảnh"
                else:
                    t0 = time.perf_counter()
                    try:
                        rec["text"] = run(p)
                    except Exception as e:
                        rec["error"] = f"{type(e).__name__}: {e}"
                    rec["seconds"] = round(time.perf_counter() - t0, 3)
                json.dump(rec, open(edir / f"{i}.json", "w", encoding="utf-8"), ensure_ascii=False)
                print(f"[{eng}] {n}/{len(todo)} {i} {rec['seconds']}s {rec['error'] or ''}")
            json.dump({"vram_mb": peak_vram_mb()}, open(meta_path, "w"))
        vram = json.load(open(meta_path))["vram_mb"] if meta_path.exists() else None

        tot = dict(gc=0, gh=0, n_ing=0, ie=0, idn=0, ifz=0, n_w=0, we=0, wd=0, wf=0)
        macro, secs, fails = [], [], 0
        for i in ids:
            fp = edir / f"{i}.json"
            if not fp.exists():
                continue
            rec = json.load(open(fp, encoding="utf-8"))
            g = gold[i]
            ocr_norm = norm_text(rec["text"])
            ocr_nd = strip_diac(ocr_norm)
            gcodes = set().union(*[extract_ins(s) for s in g.get("gold_additives_raw", [])]) if g.get("gold_additives_raw") else set()
            hit = gcodes & extract_ins(rec["text"])
            ni, ie, idn, ifz = coverage(g.get("gold_ingredients_raw", []), ocr_norm, ocr_nd, args.fuzzy_threshold)
            nw, we, wd, wf = coverage(g.get("gold_warning_raw", []), ocr_norm, ocr_nd, args.fuzzy_threshold)
            tot["gc"] += len(gcodes); tot["gh"] += len(hit)
            for k, v in zip(("n_ing", "ie", "idn", "ifz", "n_w", "we", "wd", "wf"), (ni, ie, idn, ifz, nw, we, wd, wf)):
                tot[k] += v
            if gcodes:
                macro.append(len(hit) / len(gcodes))
            if rec["error"]:
                fails += 1
            elif rec["seconds"] is not None:
                secs.append(rec["seconds"])
            per_image.append(dict(engine=eng, id=i, n_gold_codes=len(gcodes), codes_hit=len(hit),
                                  n_ing=ni, ing_exact=ie, ing_nodiac=idn, ing_fuzzy=ifz,
                                  n_warn=nw, warn_exact=we, warn_nodiac=wd, warn_fuzzy=wf,
                                  seconds=rec["seconds"], error=rec["error"] or ""))
        summaries.append(dict(
            engine=eng, n_images=len(ids), failed=fails,
            ins_recall_micro=pct(tot["gh"], tot["gc"]),
            ins_recall_macro=pct(sum(macro), len(macro)) if macro else None,
            ing_exact=pct(tot["ie"], tot["n_ing"]), ing_nodiac=pct(tot["idn"], tot["n_ing"]), ing_fuzzy=pct(tot["ifz"], tot["n_ing"]),
            warn_exact=pct(tot["we"], tot["n_w"]), warn_nodiac=pct(tot["wd"], tot["n_w"]), warn_fuzzy=pct(tot["wf"], tot["n_w"]),
            sec_per_image=round(sum(secs) / len(secs), 2) if secs else None, vram_mb=vram))

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in (("per_image.csv", per_image), ("summary.csv", summaries)):
        if rows:
            with open(out_dir / name, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

    print("\n=== TÓM TẮT (đơn vị %, trừ giây và MB) ===")
    cols = list(summaries[0])
    print(" | ".join(cols))
    for s in summaries:
        print(" | ".join(str(s[c]) for c in cols))

    # luật chọn đã định trước: hơn >= margin điểm INS recall thì thắng; không thì chọn engine nhanh hơn
    ok = [s for s in summaries if s["ins_recall_micro"] is not None
          and (not args.max_vram_mb or s["vram_mb"] is None or s["vram_mb"] <= args.max_vram_mb)
          and (not args.max_sec or s["sec_per_image"] is None or s["sec_per_image"] <= args.max_sec)]
    if len(ok) >= 2:
        best = max(s["ins_recall_micro"] for s in ok)
        close = [s for s in ok if s["ins_recall_micro"] >= best - args.margin]
        win = min(close, key=lambda s: s["sec_per_image"] if s["sec_per_image"] is not None else 1e9)
        why = "hơn hẳn về INS recall" if len(close) == 1 else f"INS recall chênh < {args.margin} điểm nên chọn engine nhanh hơn"
        print(f"\nTheo luật đã định: chọn '{win['engine']}' ({why}).")
    print(f"\nĐã ghi: {out_dir}/summary.csv, {out_dir}/per_image.csv")


if __name__ == "__main__":
    main()