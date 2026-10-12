"""Entry points for benchmark and demo charts; each family lives in evaluation_charts."""
from __future__ import annotations

from io import BytesIO
from typing import Any

from .models import InputError
from .solver import METHODS
from .evaluation_charts.common import (
    FAMILIES as FAMILIES,
    GROUP_LABELS as GROUP_LABELS,
    MAP_LABELS as MAP_LABELS,
    METRIC_LABELS as METRIC_LABELS,
    METHOD_STYLES as METHOD_STYLES,
    _eligible_seed_runs as _eligible_seed_runs,
    _instance_labels as _instance_labels,
    _label_caption as _label_caption,
    _runs_by_instance,
    _slug as _slug,
    _spec,
    representative_instances as representative_instances,
    families_for as families_for,
)
from .evaluation_charts.quality import build_figures as _quality
from .evaluation_charts.components import build_figures as _components
from .evaluation_charts.stability import build_figures as _stability
from .evaluation_charts.convergence import build_figures as _convergence
from .evaluation_charts.scalability import (
    _controlled_layout as _controlled_layout,
    build_figures as _scalability,
)


def figure_specs(payload: dict, reference: str = "B2", group: str | None = None,
                 style: str = "report") -> list[dict[str, Any]]:
    """Return core figures and planned sensitivity, with unavailable reasons."""
    from .evaluation import evaluation_tables, validate_evaluation

    validate_evaluation(payload)
    return _figure_specs_from_tables(payload, evaluation_tables(payload, reference=reference), reference, group, style)


def _figure_specs_from_tables(payload: dict, tables: dict, reference: str = "B2", group: str | None = None,
                             style: str = "report") -> list[dict[str, Any]]:
    """Render prepared tables; the caller must have validated this exact payload."""
    if style not in ("report", "presentation"):
        raise InputError("Figure style must be report or presentation")
    if reference not in METHODS:
        raise InputError(f"Unknown reference method: {reference}")
    selected = [g for g in payload["groups"] if group is None or g["name"] == group]
    if not selected:
        raise InputError(f"Unknown evaluation group: {group}")
    try:
        import matplotlib
    except ImportError:
        return [_spec(g, family, reason="Cần cài Matplotlib để tạo biểu đồ; bảng CSV vẫn dùng được.")
                for g in selected for family in families_for(g)]
    font = 20 if style == "presentation" else 10
    specs = []
    with matplotlib.rc_context({"font.family": "DejaVu Sans", "font.size": font,
                                "axes.titlesize": font, "axes.labelsize": font,
                                "xtick.labelsize": font - 1, "ytick.labelsize": font - 1,
                                "figure.titlesize": font + 2, "svg.fonttype": "none", "pdf.fonttype": 42}):
        for selected_group in selected:
            if "sensitivity_condition" in selected_group["config"]:
                continue
            rows = [row for row in tables["per_instance"] if row["group"] == selected_group["name"]]
            runs = _runs_by_instance(selected_group)
            specs.extend(_quality(selected_group, rows, reference, style))
            specs.extend(_components(selected_group, rows, reference, style))
            specs.extend(_stability(selected_group, runs, style))
            specs.extend(_convergence(selected_group, runs, style))
            specs.extend(_scalability(selected_group, rows, reference, style))
            from .evaluation_charts.sensitivity import build_figures
            specs.extend(build_figures(payload, selected_group, tables, style))
    return specs


def figure_bytes(figure: Any, format: str = "png") -> bytes:
    """Render a figure in PNG (300 dpi), PDF, or SVG for export or download."""
    format = format.lower()
    if format not in ("png", "pdf", "svg"):
        raise InputError("Figure format must be png, pdf or svg")
    if figure is None:
        raise InputError("Cannot render an unavailable figure")
    buffer = BytesIO()
    if getattr(figure, "_evaluation_style", "report") == "presentation":
        import matplotlib
        with matplotlib.rc_context({"savefig.bbox": None}):
            figure.savefig(buffer, format=format, dpi=300, facecolor="white", bbox_inches=None)
    else:
        figure.savefig(buffer, format=format, dpi=300, facecolor="white", bbox_inches="tight")
    return buffer.getvalue()
