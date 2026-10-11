import pandas as pd
df = pd.read_csv("/home/phanthaituan/workspace/Khoa_Luan/data/reports/completeness_report_v2.csv", dtype={"image_id": str})  # dtype=str để giữ số 0 đầu
core = df[df.has_ingredient & df.has_additive]
generic = core[core.has_generic_allergy_reference]          # cảnh báo dị ứng chung chung
rest = core.drop(generic.index)
declared = rest[(rest.n_allergen_contains + rest.n_allergen_may_contain) > 0]   # khai báo cụ thể
none = rest.drop(declared.index)                            # không có dị ứng
ids = sorted(pd.concat([g.sample(min(20, len(g)), random_state=42) for g in (generic, declared, none)]).image_id)
open("/home/phanthaituan/workspace/Khoa_Luan/data/results/Benchmark/benchmark_ids.txt", "w").write("\n".join(ids))