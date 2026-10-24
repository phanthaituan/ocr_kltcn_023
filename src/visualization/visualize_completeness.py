"""
visualize_completeness.py
Tạo biểu đồ cột trực quan hóa báo cáo độ đầy đủ thông tin (completeness_report_v2.csv)
phục vụ báo cáo và khóa luận tốt nghiệp.
"""

import os
import shutil
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

def set_plot_style():
    sns.set_theme(style="whitegrid")
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial", "Liberation Sans", "sans-serif"]
    plt.rcParams["axes.edgecolor"] = "#cccccc"
    plt.rcParams["axes.linewidth"] = 0.8
    plt.rcParams["grid.color"] = "#eeeeee"
    plt.rcParams["grid.linestyle"] = "--"
    plt.rcParams["grid.alpha"] = 0.7

def load_data(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    return df

def generate_visualizations(csv_path: str, output_dir: str, artifact_dir: str = None):
    os.makedirs(output_dir, exist_ok=True)
    df = load_data(csv_path)
    n_total = len(df)

    set_plot_style()

    # ----------------------------------------------------
    # 1. COMPREHENSIVE 4-PANEL DASHBOARD
    # ----------------------------------------------------
    fig, axes = plt.subplots(2, 2, figsize=(15, 12), dpi=300)
    fig.suptitle(
        f"Báo cáo trực quan hóa độ đầy đủ thông tin nhãn thực phẩm (N = {n_total} mẫu)",
        fontsize=16,
        fontweight="bold",
        y=0.98,
        color="#1a202c"
    )

    # Panel A: Tỷ lệ xuất hiện trường thông tin
    ax_a = axes[0, 0]
    fields = [
        ("Thành phần\n(has_ingredient)", df["has_ingredient"].sum()),
        ("Dinh dưỡng\n(has_nutrition)", df["has_nutrition"].sum()),
        ("Cảnh báo\n(has_warning)", df["has_warning"].sum()),
        ("Phụ gia\n(has_additive)", df["has_additive"].sum()),
        ("Đầy đủ 4 trường\n(core 4/4)", ((df["has_ingredient"]) & (df["has_additive"]) & (df["has_nutrition"]) & (df["has_warning"])).sum()),
        ("Dị ứng chung\n(has_generic_allergy)", df["has_generic_allergy_reference"].sum()),
    ]
    labels_a = [item[0] for item in fields]
    counts_a = [item[1] for item in fields]
    pcts_a = [(c / n_total) * 100 for c in counts_a]
    colors_a = ["#2b6cb0", "#319795", "#d69e2e", "#dd6b20", "#38a169", "#718096"]

    bars_a = ax_a.bar(labels_a, pcts_a, color=colors_a, width=0.6, edgecolor="#ffffff", linewidth=1.2)
    ax_a.set_title("A. Tỷ lệ xuất hiện các trường thông tin trên nhãn (%)", fontsize=12, fontweight="bold", pad=12)
    ax_a.set_ylabel("Tỷ lệ phần trăm (%)", fontsize=10)
    ax_a.set_ylim(0, 115)
    ax_a.axhline(100, color="#a0aec0", linestyle=":", linewidth=1)

    for bar, count, pct in zip(bars_a, counts_a, pcts_a):
        height = bar.get_height()
        ax_a.annotate(
            f"{pct:.1f}%\n({count}/{n_total})",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
            color="#2d3748",
        )

    # Panel B: Phân bố số trường thông tin cốt lõi (0 to 4)
    ax_b = axes[0, 1]
    core_cols = ["has_ingredient", "has_additive", "has_nutrition", "has_warning"]
    df["core_fields_count"] = df[core_cols].sum(axis=1)
    core_counts = df["core_fields_count"].value_counts().reindex(range(5), fill_value=0)
    core_pcts = (core_counts / n_total) * 100
    labels_b = [f"{i}/4 trường" for i in range(5)]
    colors_b = ["#e53e3e", "#dd6b20", "#d69e2e", "#4299e1", "#38a169"]

    bars_b = ax_b.bar(labels_b, core_counts, color=colors_b, width=0.55, edgecolor="#ffffff", linewidth=1.2)
    ax_b.set_title("B. Mức độ đầy đủ thông tin cốt lõi trên mỗi sản phẩm", fontsize=12, fontweight="bold", pad=12)
    ax_b.set_ylabel("Số lượng sản phẩm", fontsize=10)
    ax_b.set_ylim(0, max(core_counts) * 1.2)

    for bar, count, pct in zip(bars_b, core_counts, core_pcts):
        if count > 0:
            height = bar.get_height()
            ax_b.annotate(
                f"{count} mẫu\n({pct:.1f}%)",
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
                color="#2d3748",
            )
        else:
            ax_b.annotate(
                "0 (0%)",
                xy=(bar.get_x() + bar.get_width() / 2, 0),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=9,
                color="#a0aec0",
            )

    # Panel C: Số lượng thực thể trung bình trên mỗi nhãn
    ax_c = axes[1, 0]
    entity_stats = [
        ("Thành phần\n(n_ingredients)", df["n_ingredients"].mean(), df["n_ingredients"].sum(), df["n_ingredients"].max()),
        ("Phụ gia\n(n_additives)", df["n_additives"].mean(), df["n_additives"].sum(), df["n_additives"].max()),
        ("Dị ứng: chứa\n(allergen_contains)", df["n_allergen_contains"].mean(), df["n_allergen_contains"].sum(), df["n_allergen_contains"].max()),
        ("Dị ứng: có thể\n(may_contain)", df["n_allergen_may_contain"].mean(), df["n_allergen_may_contain"].sum(), df["n_allergen_may_contain"].max()),
        ("Suy luận từ TP\n(inferred)", df["n_inferred_from_ingredient"].mean(), df["n_inferred_from_ingredient"].sum(), df["n_inferred_from_ingredient"].max()),
    ]
    labels_c = [item[0] for item in entity_stats]
    means_c = [item[1] for item in entity_stats]
    totals_c = [item[2] for item in entity_stats]
    colors_c = ["#3182ce", "#805ad5", "#e53e3e", "#dd6b20", "#319795"]

    bars_c = ax_c.bar(labels_c, means_c, color=colors_c, width=0.55, edgecolor="#ffffff", linewidth=1.2)
    ax_c.set_title("C. Số lượng thực thể trung bình trích xuất trên mỗi nhãn", fontsize=12, fontweight="bold", pad=12)
    ax_c.set_ylabel("Số lượng trung bình (Mean)", fontsize=10)
    ax_c.set_ylim(0, max(means_c) * 1.25)

    for bar, mean_val, tot in zip(bars_c, means_c, totals_c):
        height = bar.get_height()
        ax_c.annotate(
            f"TB: {mean_val:.2f}\n(Tổng: {tot:,})",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
            color="#2d3748",
        )

    # Panel D: Phân bố số lượng thành phần và phụ gia theo dải
    ax_d = axes[1, 1]
    bins = [-1, 0, 5, 10, 15, 100]
    bin_labels = ["0", "1-5", "6-10", "11-15", ">15"]
    ing_binned = pd.cut(df["n_ingredients"], bins=bins, labels=bin_labels).value_counts().reindex(bin_labels)
    add_binned = pd.cut(df["n_additives"], bins=bins, labels=bin_labels).value_counts().reindex(bin_labels)

    x = np.arange(len(bin_labels))
    width = 0.35

    bar_ing = ax_d.bar(x - width / 2, ing_binned, width, label="Thành phần (n_ingredients)", color="#3182ce", edgecolor="#ffffff")
    bar_add = ax_d.bar(x + width / 2, add_binned, width, label="Phụ gia (n_additives)", color="#805ad5", edgecolor="#ffffff")

    ax_d.set_title("D. Phân bố tần suất số lượng theo khoảng", fontsize=12, fontweight="bold", pad=12)
    ax_d.set_xlabel("Khoảng số lượng thực thể trên một nhãn", fontsize=10)
    ax_d.set_ylabel("Số lượng sản phẩm", fontsize=10)
    ax_d.set_xticks(x)
    ax_d.set_xticklabels(bin_labels)
    ax_d.legend(frameon=True, facecolor="#f7fafc", edgecolor="#cbd5e0")
    ax_d.set_ylim(0, max(max(ing_binned), max(add_binned)) * 1.2)

    for bar in bar_ing:
        h = bar.get_height()
        ax_d.annotate(f"{int(h)}", xy=(bar.get_x() + bar.get_width() / 2, h), xytext=(0, 3),
                      textcoords="offset points", ha="center", va="bottom", fontsize=8, fontweight="bold", color="#2b6cb0")

    for bar in bar_add:
        h = bar.get_height()
        ax_d.annotate(f"{int(h)}", xy=(bar.get_x() + bar.get_width() / 2, h), xytext=(0, 3),
                      textcoords="offset points", ha="center", va="bottom", fontsize=8, fontweight="bold", color="#6b46c1")

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    comprehensive_path = os.path.join(output_dir, "completeness_comprehensive_barchart.png")
    plt.savefig(comprehensive_path, dpi=300)
    plt.close()

    # ----------------------------------------------------
    # 2. STANDALONE FOCUSED BAR CHART: TỶ LỆ HOÀN THIỆN TRƯỜNG THÔNG TIN
    # (Thích hợp chèn vào slide hoặc báo cáo tiểu luận)
    # ----------------------------------------------------
    fig_f, ax_f = plt.subplots(figsize=(10, 6), dpi=300)
    
    # Sort by percentage
    sorted_data = sorted(
        [
            ("Thành phần (Ingredients)", df["has_ingredient"].sum(), (df["has_ingredient"].sum() / n_total) * 100),
            ("Bảng dinh dưỡng (Nutrition)", df["has_nutrition"].sum(), (df["has_nutrition"].sum() / n_total) * 100),
            ("Cảnh báo an toàn (Warnings)", df["has_warning"].sum(), (df["has_warning"].sum() / n_total) * 100),
            ("Phụ gia thực phẩm (Additives)", df["has_additive"].sum(), (df["has_additive"].sum() / n_total) * 100),
            ("Đầy đủ 4 trường cốt lõi (All 4 Core)", df["core_fields_count"].eq(4).sum(), (df["core_fields_count"].eq(4).sum() / n_total) * 100),
            ("Cảnh báo dị ứng chung (Generic Allergy)", df["has_generic_allergy_reference"].sum(), (df["has_generic_allergy_reference"].sum() / n_total) * 100),
        ],
        key=lambda x: x[2],
        reverse=False
    )
    
    y_pos = np.arange(len(sorted_data))
    f_labels = [x[0] for x in sorted_data]
    f_counts = [x[1] for x in sorted_data]
    f_pcts = [x[2] for x in sorted_data]
    f_colors = ["#718096" if "Allergy" in l else "#38a169" if "Core" in l else "#3182ce" for l in f_labels]

    hbars = ax_f.barh(y_pos, f_pcts, color=f_colors, height=0.55, edgecolor="#ffffff", linewidth=1.2)
    ax_f.set_yticks(y_pos)
    ax_f.set_yticklabels(f_labels, fontsize=10, fontweight="bold")
    ax_f.set_xlabel("Tỷ lệ xuất hiện trên nhãn (%)", fontsize=11, fontweight="bold")
    ax_f.set_title(f"Tỷ lệ hoàn thiện các trường thông tin trên nhãn thực phẩm (N = {n_total})", fontsize=13, fontweight="bold", pad=15)
    ax_f.set_xlim(0, 115)
    ax_f.axvline(100, color="#cbd5e0", linestyle="--", linewidth=1)

    for bar, count, pct in zip(hbars, f_counts, f_pcts):
        width = bar.get_width()
        ax_f.annotate(
            f" {pct:.1f}% ({count}/{n_total} nhãn)",
            xy=(width, bar.get_y() + bar.get_height() / 2),
            xytext=(6, 0),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=9.5,
            fontweight="bold",
            color="#2d3748"
        )

    plt.tight_layout()
    standalone_path = os.path.join(output_dir, "completeness_field_presence.png")
    plt.savefig(standalone_path, dpi=300)
    plt.close()

    print(f"Generated: {comprehensive_path}")
    print(f"Generated: {standalone_path}")

    # Copy to artifact directory if provided
    if artifact_dir:
        os.makedirs(artifact_dir, exist_ok=True)
        shutil.copy(comprehensive_path, os.path.join(artifact_dir, "completeness_comprehensive_barchart.png"))
        shutil.copy(standalone_path, os.path.join(artifact_dir, "completeness_field_presence.png"))
        print(f"Copied images to artifact directory: {artifact_dir}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/reports/completeness_report_v2.csv")
    parser.add_argument("--out", default="data/reports")
    parser.add_argument("--artifact_dir", default="/home/phanthaituan/.gemini/antigravity/brain/e6864ed0-04d8-4b6b-942f-2b6fc7e93f68")
    args = parser.parse_args()

    generate_visualizations(args.csv, args.out, args.artifact_dir)

