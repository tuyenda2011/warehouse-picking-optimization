import sys
from pathlib import Path
from itertools import pairwise
import shutil
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.generator import generate_scenario
from src.models import read_instance

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial", "Liberation Sans", "Tahoma"]


def draw_synthetic_map(ax, instance, title, subtitle="", highlight_cross=False, show_abc=False, is_rush=False):
    ax.set_facecolor("#ffffff")
    nodes = {n.id: n for n in instance.nodes}
    layout = instance.metadata.get("layout", {})
    aisles = layout.get("aisles", [])
    cross_rows = sorted(layout.get("cross_aisles", []))

    # 1. Storage racks
    for left, right in pairwise(aisles):
        a, b = nodes[left[0]], nodes[right[0]]
        bounds = [0] + cross_rows + [len(left) - 1]
        for r_start, r_end in pairwise(bounds):
            y_bot = nodes[left[r_start]].y
            y_top = nodes[left[r_end]].y
            w = b.x - a.x - 2.8
            h = y_top - y_bot - 4.0
            if w > 1 and h > 1:
                rect = Rectangle(
                    (a.x + 1.4, y_bot + 2.0),
                    w, h,
                    facecolor="#e2e8f0",
                    edgecolor="#94a3b8",
                    linewidth=0.85,
                    zorder=1
                )
                ax.add_patch(rect)

    # 2. Network edges (aisles and cross-aisles)
    for edge in instance.edges:
        p1, p2 = nodes[edge.source], nodes[edge.target]
        is_cross = False
        if highlight_cross and cross_rows:
            for cr in cross_rows:
                y_cross = nodes[aisles[0][cr]].y
                if abs(p1.y - y_cross) < 1e-4 and abs(p2.y - y_cross) < 1e-4 and abs(p1.x - p2.x) > 1e-4:
                    is_cross = True
                    break

        if is_cross:
            ax.plot([p1.x, p2.x], [p1.y, p2.y], color="#0284c7", linewidth=2.3, linestyle="--", zorder=3)
        else:
            ax.plot([p1.x, p2.x], [p1.y, p2.y], color="#cbd5e1", linewidth=1.5, zorder=2)

    # 3. Product pick locations (SKU)
    demand_zones = instance.metadata.get("demand_zones")
    if show_abc and demand_zones:
        zone_a = set(demand_zones.get("A", []))
        zone_b = set(demand_zones.get("B", []))
        zone_c = set(demand_zones.get("C", []))

        prods_a = [nodes[p.location] for p in instance.products if p.id in zone_a]
        prods_b = [nodes[p.location] for p in instance.products if p.id in zone_b]
        prods_c = [nodes[p.location] for p in instance.products if p.id in zone_c]

        if prods_c:
            ax.scatter([n.x for n in prods_c], [n.y for n in prods_c], s=40, color="#3b82f6", edgecolor="white", linewidth=0.6, zorder=4, label="Vùng C (10% nhu cầu)")
        if prods_b:
            ax.scatter([n.x for n in prods_b], [n.y for n in prods_b], s=46, color="#f59e0b", edgecolor="white", linewidth=0.7, zorder=5, label="Vùng B (20% nhu cầu)")
        if prods_a:
            ax.scatter([n.x for n in prods_a], [n.y for n in prods_a], s=58, color="#ef4444", edgecolor="white", linewidth=0.8, zorder=6, label="Vùng A (70% nhu cầu)")
    elif is_rush:
        prod_nodes = [nodes[p.location] for p in instance.products]
        ax.scatter([n.x for n in prod_nodes], [n.y for n in prod_nodes], s=44, color="#e11d48", edgecolor="white", linewidth=0.7, zorder=4, label="SKU (Hạn gấp λ=0.06)")
    else:
        prod_nodes = [nodes[p.location] for p in instance.products]
        ax.scatter([n.x for n in prod_nodes], [n.y for n in prod_nodes], s=44, color="#2563eb", edgecolor="white", linewidth=0.7, zorder=4, label="Vị trí SKU")

    # 4. Depot
    depot = nodes[instance.depot]
    ax.scatter([depot.x], [depot.y], s=160, marker="s", color="#0f172a", edgecolor="#fbbf24", linewidth=1.5, zorder=7)
    ax.annotate("Depot (0,0)", (depot.x, depot.y), xytext=(7, -13), textcoords="offset points",
                fontsize=9.0, fontweight="bold", color="#0f172a",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="#ffffff", edgecolor="#cbd5e1", alpha=0.9))

    # 5. Annotation for cross aisle
    if highlight_cross and cross_rows:
        if len(cross_rows) == 1:
            y_mid = nodes[aisles[0][cross_rows[0]]].y
            x_mid = nodes[aisles[-1][0]].x
            ax.annotate("Lối giữa", xy=(x_mid, y_mid),
                        xytext=(x_mid + 2.0, y_mid + 2.5),
                        arrowprops=dict(arrowstyle="->", color="#0284c7", lw=1.1),
                        fontsize=8.0, color="#0284c7", fontweight="bold")
        elif len(cross_rows) > 1:
            for i, cr in enumerate(cross_rows, start=1):
                y_cr = nodes[aisles[0][cr]].y
                x_cr = nodes[aisles[-1][0]].x
                ax.annotate(f"Lối ngang {i}", xy=(x_cr, y_cr),
                            xytext=(x_cr + 2.0, y_cr + 2.0),
                            arrowprops=dict(arrowstyle="->", color="#0284c7", lw=1.1),
                            fontsize=7.8, color="#0284c7", fontweight="bold")

    ax.set_title(f"{title}\n{subtitle}", fontsize=10.2, fontweight="bold", pad=9, color="#1e293b", linespacing=1.28)
    ax.set_aspect("equal")
    ax.margins(0.07)
    for spine in ax.spines.values():
        spine.set_color("#cbd5e1")
        spine.set_linewidth(0.8)
    ax.tick_params(colors="#64748b", labelsize=8.0)
    ax.grid(True, linestyle=":", alpha=0.35, color="#94a3b8")
    ax.legend(loc="upper right", fontsize=8.0, framealpha=0.92, edgecolor="#cbd5e1")


def main():
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "report" / "image" / "benchmark_report_01" / "01_maps"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load all 5 simulation scenarios
    sb = generate_scenario("single_block")
    db = generate_scenario("double_block")
    rh = generate_scenario("rush_hour")
    mh = generate_scenario("mega_hub")
    abc = generate_scenario("abc_zonal")

    # 2. Combined Figure for all 5 simulation scenarios
    # Row 1 has 3 columns: (a) Kho chuẩn, (b) Kho 2 khối, (c) Cao điểm
    # Row 2 has 2 columns: (d) Đại kho vận Mega Hub, (e) Phân khu ABC
    fig = plt.figure(figsize=(15.5, 11.5), layout="constrained")
    fig.patch.set_facecolor("#ffffff")
    gs = fig.add_gridspec(2, 6)

    ax1 = fig.add_subplot(gs[0, 0:2])
    ax2 = fig.add_subplot(gs[0, 2:4])
    ax3 = fig.add_subplot(gs[0, 4:6])
    ax4 = fig.add_subplot(gs[1, 0:3])
    ax5 = fig.add_subplot(gs[1, 3:6])

    draw_synthetic_map(
        ax1, sb,
        title="(a) Kho Chuẩn (Single-Block)",
        subtitle="5 dãy x 6 hàng (30 SKU) • 0 lối giữa • λ=0.15",
        highlight_cross=False, show_abc=False
    )
    draw_synthetic_map(
        ax2, db,
        title="(b) Kho 2 Khối (Double-Block)",
        subtitle="6 dãy x 8 hàng (48 SKU) • 1 lối cắt ngang (2 blocks) • λ=0.18",
        highlight_cross=True, show_abc=False
    )
    draw_synthetic_map(
        ax3, rh,
        title="(c) Giờ Cao Điểm (Rush Hour)",
        subtitle="6 dãy x 8 hàng (48 SKU) • 4 NV, tải 20 • Hạn cực gấp λ=0.06",
        highlight_cross=True, show_abc=False, is_rush=True
    )
    draw_synthetic_map(
        ax4, mh,
        title="(d) Đại Kho Vận (Mega Hub)",
        subtitle="10 dãy x 16 hàng (160 SKU) • 2 lối ngang cắt giữa (3 blocks) • λ=0.20",
        highlight_cross=True, show_abc=False
    )
    draw_synthetic_map(
        ax5, abc,
        title="(e) Phân Khu Tần Suất (ABC Zonal Layout)",
        subtitle="6 dãy x 10 hàng (60 SKU) • Vùng A (gần depot) chiếm 70% nhu cầu",
        highlight_cross=True, show_abc=True
    )

    sim_path = out_dir / "01_simulation_warehouse_topologies.png"
    fig.savefig(sim_path, dpi=300)
    plt.close(fig)
    print(f"Saved all 5 simulation warehouse topologies: {sim_path}")

    # Copy to artifact directory
    artifact_dir = Path(r"C:\Users\Admin\.gemini\antigravity-ide\brain\912002ec-b1f9-41a4-80c7-f3ecb14cb345")
    if artifact_dir.exists():
        dest = artifact_dir / sim_path.name
        shutil.copy2(sim_path, dest)
        print(f"Copied to artifact: {dest}")


if __name__ == "__main__":
    main()
