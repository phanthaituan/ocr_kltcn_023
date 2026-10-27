"""
make_split.py
Chia 521 ảnh Core (có đủ cả ingredient và additive) thành 3 tập không giao nhau:
  - dev  (~70 ảnh) : Bắt buộc chứa toàn bộ 60 ảnh benchmark OCR + ~10 ảnh lấy mẫu phân tầng
  - test (~200 ảnh): Tập đánh giá cuối cùng (đóng băng, chỉ chạy 1 lần ở Tuần 4)
  - pool (~251 ảnh): Tập nguồn để xây từ điển cho P0/P1 (đảm bảo không rò rỉ dữ liệu sang dev/test)

Các ảnh ngoài Core (79/600 ảnh thiếu ingredient hoặc additive) được lưu vào `non_core.json`.
Nếu chưa có file `benchmark_ids.txt`, script sẽ tự động sinh 60 ảnh benchmark theo đúng quy tắc
20/20/20 (generic allergy / declared allergy / no allergy) với random_state=42.

Phân tầng (Stratification) dựa trên tổ hợp khóa `(has_allergen, has_adi_warning_all_numeric)`
để tỷ lệ nhãn dương Dị ứng và ADI đồng đều tuyệt đối giữa Dev, Test và Pool.

Cách chạy (từ thư mục gốc project):
    python src/data_pipeline/make_split.py
"""

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.common.paths import ADI_LABELS_DIR, BENCHMARK_IDS_TXT, COMPLETENESS_REPORT, SPLITS_DIR


def parse_bool(val) -> bool:
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("true", "1", "yes")


def load_completeness_report(report_path: Path) -> list:
    with open(report_path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_adi_map(adi_labels_dir: Path) -> dict:
    """Đọc nhãn ADI từ thư mục ADI_LABELS_DIR (sinh bởi join_adi_labels.py)."""
    adi_map = {}
    if not adi_labels_dir.exists():
        return adi_map
    for fp in sorted(adi_labels_dir.glob("*.json")):
        rec = json.load(open(fp, encoding="utf-8"))
        img_id = str(rec.get("image_id", fp.stem))
        adi_map[img_id] = {
            "has_adi_all": bool(rec.get("has_adi_warning_all_numeric", False)),
            "has_adi_strict": bool(rec.get("has_adi_warning_strict_adi", False)),
        }
    return adi_map


def ensure_benchmark_ids(core_rows: list, benchmark_path: Path, seed: int = 42) -> list:
    """
    Đọc danh sách 60 ảnh benchmark từ benchmark_path.
    Nếu file chưa tồn tại, tự động lấy mẫu 20/20/20 (generic / declared / none) với seed=42.
    """
    if benchmark_path.exists():
        ids = [line.strip() for line in benchmark_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if ids:
            print(f"Đã đọc {len(ids)} ảnh benchmark từ: {benchmark_path}")
            return sorted(set(ids))

    generic = [r for r in core_rows if parse_bool(r.get("has_generic_allergy_reference", False))]
    generic_ids = {r["image_id"] for r in generic}

    rest = [r for r in core_rows if r["image_id"] not in generic_ids]
    declared = [
        r for r in rest
        if (int(r.get("n_allergen_contains", 0) or 0) + int(r.get("n_allergen_may_contain", 0) or 0)) > 0
    ]
    declared_ids = {r["image_id"] for r in declared}
    none_group = [r for r in rest if r["image_id"] not in declared_ids]

    selected = []
    for group in (generic, declared, none_group):
        rng = random.Random(seed)
        g_sorted = sorted(group, key=lambda x: x["image_id"])
        k = min(20, len(g_sorted))
        selected.extend(r["image_id"] for r in rng.sample(g_sorted, k))

    selected = sorted(set(selected))
    benchmark_path.parent.mkdir(parents=True, exist_ok=True)
    benchmark_path.write_text("\n".join(selected) + "\n", encoding="utf-8")
    print(f"Đã tự động tạo {len(selected)} ảnh benchmark (20/20/20) tại: {benchmark_path}")
    return selected


def stratified_sample(items: list, k: int, strata_fn, seed: int = 42) -> list:
    """Lấy mẫu phân tầng k phần tử từ danh sách items theo khóa strata_fn(item)."""
    if k <= 0:
        return []
    if k >= len(items):
        return list(items)

    buckets = defaultdict(list)
    for it in items:
        buckets[strata_fn(it)].append(it)

    total = len(items)
    chosen = []
    remainders = []

    for s_key in sorted(buckets.keys()):
        group = sorted(buckets[s_key], key=lambda x: x["image_id"])
        rng = random.Random(seed)
        rng.shuffle(group)

        exact = len(group) * (k / total)
        n_take = int(exact)
        chosen.extend(group[:n_take])
        remainders.append((exact - n_take, s_key, group[n_take:]))

    # Phân bổ phần dư theo thứ tự phần thập phân giảm dần
    remainders.sort(key=lambda x: (-x[0], x[1]))
    idx = 0
    while len(chosen) < k and idx < len(remainders):
        _, _, leftover = remainders[idx]
        if leftover:
            chosen.append(leftover.pop(0))
        idx += 1

    return sorted(chosen, key=lambda x: x["image_id"])


def summarize_split(name: str, rows: list) -> dict:
    n = len(rows)
    if n == 0:
        return {"split": name, "count": 0}
    n_allergen = sum(1 for r in rows if r["has_allergen"])
    n_adi_all = sum(1 for r in rows if r["has_adi_all"])
    n_adi_strict = sum(1 for r in rows if r["has_adi_strict"])
    return {
        "split": name,
        "count": n,
        "has_allergen": f"{n_allergen} ({100*n_allergen/n:.1f}%)",
        "has_adi_all_numeric": f"{n_adi_all} ({100*n_adi_all/n:.1f}%)",
        "has_adi_strict": f"{n_adi_strict} ({100*n_adi_strict/n:.1f}%)",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report_csv", default=str(COMPLETENESS_REPORT), help="Đường dẫn completeness_report CSV")
    ap.add_argument("--adi_labels_dir", default=str(ADI_LABELS_DIR), help="Thư mục chứa adi_labels JSON")
    ap.add_argument("--splits_dir", default=str(SPLITS_DIR), help="Thư mục xuất các file split")
    ap.add_argument("--benchmark_ids", default=str(BENCHMARK_IDS_TXT), help="Đường dẫn file benchmark_ids.txt (mặc định: data/results/Benchmark/benchmark_ids.txt, bộ ảnh đã chạy OCR benchmark)")
    ap.add_argument("--dev_size", type=int, default=70, help="Tổng số ảnh tập dev (bao gồm 60 ảnh benchmark)")
    ap.add_argument("--test_size", type=int, default=200, help="Tổng số ảnh tập test")
    ap.add_argument("--seed", type=int, default=42, help="Random seed cố định")
    args = ap.parse_args()

    report_path = Path(args.report_csv)
    if not report_path.exists():
        # Fallback kiểm tra file completeness_report.csv nếu tên _v2 chưa tồn tại
        alt_path = report_path.with_name("completeness_report.csv")
        if alt_path.exists():
            report_path = alt_path
        else:
            print(f"Không tìm thấy báo cáo độ đầy đủ tại: {report_path}. Hãy chạy parse_vifoodlabel.py trước.")
            sys.exit(1)

    splits_dir = Path(args.splits_dir)
    splits_dir.mkdir(parents=True, exist_ok=True)
    benchmark_path = Path(args.benchmark_ids)

    raw_rows = load_completeness_report(report_path)
    adi_map = load_adi_map(Path(args.adi_labels_dir))
    if not adi_map:
        print("[!] Cảnh báo: Chưa có dữ liệu trong ADI_LABELS_DIR. Phân tầng chỉ dựa trên nhãn dị ứng.")

    core_rows = []
    non_core_rows = []

    for r in raw_rows:
        img_id = str(r["image_id"]).strip()
        is_core = parse_bool(r.get("has_ingredient", False)) and parse_bool(r.get("has_additive", False))
        has_allergen = (
            int(r.get("n_allergen_contains", r.get("n_allergen_contains_hints", 0)) or 0)
            + int(r.get("n_allergen_may_contain", r.get("n_allergen_may_contain_hints", 0)) or 0)
        ) > 0
        adi_info = adi_map.get(img_id, {"has_adi_all": False, "has_adi_strict": False})

        enriched = {
            **r,
            "image_id": img_id,
            "is_core": is_core,
            "has_allergen": has_allergen,
            "has_adi_all": adi_info["has_adi_all"],
            "has_adi_strict": adi_info["has_adi_strict"],
        }
        if is_core:
            core_rows.append(enriched)
        else:
            non_core_rows.append(enriched)

    benchmark_ids = ensure_benchmark_ids(core_rows, benchmark_path, seed=args.seed)
    bench_set = set(benchmark_ids)

    dev_bench_rows = [r for r in core_rows if r["image_id"] in bench_set]
    remaining_core = [r for r in core_rows if r["image_id"] not in bench_set]

    strata_fn = lambda x: (x["has_allergen"], x["has_adi_all"])

    n_extra_dev = max(0, args.dev_size - len(dev_bench_rows))
    dev_extra_rows = stratified_sample(remaining_core, n_extra_dev, strata_fn, seed=args.seed)
    dev_rows = sorted(dev_bench_rows + dev_extra_rows, key=lambda x: x["image_id"])
    dev_ids_set = {r["image_id"] for r in dev_rows}

    after_dev = [r for r in core_rows if r["image_id"] not in dev_ids_set]
    test_rows = stratified_sample(after_dev, args.test_size, strata_fn, seed=args.seed + 1)
    test_ids_set = {r["image_id"] for r in test_rows}

    pool_rows = sorted([r for r in after_dev if r["image_id"] not in test_ids_set], key=lambda x: x["image_id"])

    # Kiểm tra không giao nhau (zero leakage assertion)
    assert len(dev_ids_set & test_ids_set) == 0, "Lỗi rò rỉ giữa dev và test!"
    assert len(dev_ids_set & {r['image_id'] for r in pool_rows}) == 0, "Lỗi rò rỉ giữa dev và pool!"
    assert len(test_ids_set & {r['image_id'] for r in pool_rows}) == 0, "Lỗi rò rỉ giữa test và pool!"

    splits_payload = {
        "dev": dev_rows,
        "test": test_rows,
        "pool": pool_rows,
        "non_core": non_core_rows,
    }

    for sp_name, sp_rows in splits_payload.items():
        ids_list = [r["image_id"] for r in sp_rows]
        out_json = {
            "split": sp_name,
            "seed": args.seed,
            "count": len(ids_list),
            "image_ids": ids_list,
        }
        with open(splits_dir / f"{sp_name}.json", "w", encoding="utf-8") as f:
            json.dump(out_json, f, ensure_ascii=False, indent=2)
        (splits_dir / f"{sp_name}_ids.txt").write_text("\n".join(ids_list) + "\n", encoding="utf-8")

    # Ghi tổng hợp toàn bộ vào splits_overview.json
    overview = {
        "seed": args.seed,
        "total_images": len(raw_rows),
        "core_images": len(core_rows),
        "non_core_images": len(non_core_rows),
        "benchmark_in_dev": len(dev_bench_rows),
        "summary": [
            summarize_split("dev", dev_rows),
            summarize_split("test", test_rows),
            summarize_split("pool", pool_rows),
            summarize_split("non_core", non_core_rows),
        ],
    }
    with open(splits_dir / "splits_overview.json", "w", encoding="utf-8") as f:
        json.dump(overview, f, ensure_ascii=False, indent=2)

    print(f"\nĐã chia tập dữ liệu thành công -> {splits_dir}")
    for s in overview["summary"]:
        if s["count"] > 0:
            print(f"  - {s['split']:8s}: {s['count']:3d} ảnh | Dị ứng: {s['has_allergen']:14s} | ADI (all): {s['has_adi_all_numeric']:14s} | ADI (strict): {s['has_adi_strict']}")
        else:   
            print(f"  - {s['split']:8s}:   0 ảnh")


if __name__ == "__main__":
    main()
