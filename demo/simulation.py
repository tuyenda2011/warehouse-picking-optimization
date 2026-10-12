"""HTML5 Canvas replay of a validated multi-picker solution for Streamlit."""
import json
import streamlit as st
import streamlit.components.v1 as components

from src.graph import WarehouseGraph
from src.models import InputError
from src.units import time_scale_seconds, unit_label

PICKER_COLORS = [
    "#176b5b",  # P1: Teal
    "#2864ad",  # P2: Blue
    "#ad661e",  # P3: Amber
    "#80539a",  # P4: Purple
    "#b43c57",  # P5: Rose
    "#197e91",  # P6: Cyan
    "#637a28",  # P7: Olive
    "#775b46",  # P8: Brown
]


def build_simulation_data(instance, result):
    nodes_dict = {n.id: n for n in instance.nodes}
    products_dict = {p.id: p for p in instance.products}
    orders_dict = {o.id: o for o in instance.orders}
    op = instance.operations
    graph = WarehouseGraph(instance)

    edges_data = []
    for e in instance.edges:
        edges_data.append({"source": e.source, "target": e.target, "distance": e.distance})

    xs = [n.x for n in instance.nodes]
    ys = [n.y for n in instance.nodes]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    layout = instance.metadata.get("layout", {})
    cross_rows = layout.get("cross_aisles", [])
    aisles_ids = layout.get("aisles", [])

    shelf_blocks = []
    if aisles_ids and len(aisles_ids) > 1:
        for i in range(len(aisles_ids) - 1):
            left_aisle = aisles_ids[i]
            right_aisle = aisles_ids[i + 1]
            a, b = nodes_dict[left_aisle[0]], nodes_dict[right_aisle[0]]
            bounds = [0] + sorted(cross_rows) + [len(left_aisle) - 1]
            for r_idx in range(len(bounds) - 1):
                r_start, r_end = bounds[r_idx], bounds[r_idx + 1]
                y_bot = nodes_dict[left_aisle[r_start]].y
                y_top = nodes_dict[left_aisle[r_end]].y
                if b.x - a.x > 3 and y_top - y_bot > 4:
                    shelf_blocks.append({
                        "x": a.x + 1.4,
                        "y": y_bot + 2.0,
                        "w": b.x - a.x - 2.8,
                        "h": y_top - y_bot - 4.0
                    })
    elif not aisles_ids:
        # Inferred racks for benchmark instances (e.g. Kris) or custom uploads
        unique_xs = sorted(set(xs))
        unique_ys = sorted(set(ys))
        if len(unique_xs) > 1 and len(unique_ys) > 1:
            y_min, y_max = min(unique_ys), max(unique_ys)
            y_span = y_max - y_min
            steps = [x2 - x1 for x1, x2 in zip(unique_xs, unique_xs[1:]) if x2 - x1 > 0]
            if steps:
                avg_step = sum(steps) / len(steps)
                if avg_step >= 6:
                    for x1, x2 in zip(unique_xs, unique_xs[1:]):
                        dx = x2 - x1
                        if 0.6 * avg_step <= dx <= 1.4 * avg_step:
                            shelf_blocks.append({
                                "x": x1 + dx * 0.18,
                                "y": y_min + y_span * 0.04,
                                "w": dx * 0.64,
                                "h": y_span * 0.92
                            })

    pickers_data = []
    total_pickers = op.pickers

    for p_idx in range(1, total_pickers + 1):
        color = PICKER_COLORS[(p_idx - 1) % len(PICKER_COLORS)]
        batches = [b for b in result["batches"] if b["picker"] == p_idx]
        batches.sort(key=lambda b: b.get("position", b.get("start", 0)))

        segments = []
        depot_node = nodes_dict[instance.depot]

        for batch in batches:
            start_t = batch["start"]
            setup_dur = op.batch_minutes
            setup_end = start_t + setup_dur

            # 1. Setup at depot
            segments.append({
                "t_start": start_t,
                "t_end": setup_end,
                "setup_dur": setup_dur,
                "x1": depot_node.x, "y1": depot_node.y,
                "x2": depot_node.x, "y2": depot_node.y,
                "state": "setup",
                "node": instance.depot,
                "load": 0,
                "batch_id": batch["id"],
                "info": f"Chuẩn bị xe ({batch['id']})"
            })
            curr_t = setup_end
            curr_load = 0
            already_picked = set()

            # Check if any items are located at depot to be picked before departure
            depot_items = {}
            for oid in batch["orders"]:
                order = orders_dict[oid]
                for item_id, qty in order.items.items():
                    if item_id not in already_picked and products_dict[item_id].location == instance.depot:
                        depot_items[item_id] = depot_items.get(item_id, 0) + qty

            if depot_items:
                for it in depot_items:
                    already_picked.add(it)
                d_load = sum(products_dict[it].size * q for it, q in depot_items.items())
                d_pick_time = sum(products_dict[it].pick_minutes * q for it, q in depot_items.items())
                d_dur = op.location_minutes + d_pick_time
                segments.append({
                    "t_start": curr_t,
                    "t_end": curr_t + d_dur,
                    "x1": depot_node.x, "y1": depot_node.y,
                    "x2": depot_node.x, "y2": depot_node.y,
                    "state": "picking",
                    "node": instance.depot,
                    "load": curr_load + d_load,
                    "batch_id": batch["id"],
                    "info": f"Lấy {sum(depot_items.values())} sản phẩm tại {instance.depot}",
                    "pick_qty": sum(depot_items.values()),
                    "pick_load": d_load,
                    "pick_items": depot_items
                })
                curr_t += d_dur
                curr_load += d_load

            # 2. Sequential leg-by-leg routing via stops (replaying batch['walk'] if available)
            stops = batch["stops"]
            walk = tuple(batch.get("walk") or ())
            if not walk or walk[0] != instance.depot or walk[-1] != instance.depot:
                raise InputError(f"Batch {batch['id']} has no complete depot-to-depot walk")
            walk_idx = 0
            traveled_distance = 0.0

            for stop_from, stop_to in zip(stops, stops[1:]):
                if walk_idx >= len(walk) or walk[walk_idx] != stop_from:
                    raise InputError(f"Batch {batch['id']} service stops do not follow its walk")
                if stop_from == stop_to:
                    sub_path = (stop_from,)
                else:
                    try:
                        next_idx = walk.index(stop_to, walk_idx + 1)
                    except ValueError as exc:
                        raise InputError(f"Batch {batch['id']} walk misses service stop {stop_to}") from exc
                    sub_path = walk[walk_idx:next_idx + 1]
                    walk_idx = next_idx

                for u_id, v_id in zip(sub_path, sub_path[1:]):
                    try:
                        u_node, v_node = nodes_dict[u_id], nodes_dict[v_id]
                        dist = graph.adj[u_id][v_id]
                    except KeyError as exc:
                        raise InputError(f"Batch {batch['id']} walk contains an unknown edge") from exc
                    traveled_distance += dist
                    travel_dur = dist / op.speed if op.speed > 0 else 0

                    segments.append({
                        "t_start": curr_t,
                        "t_end": curr_t + travel_dur,
                        "x1": u_node.x, "y1": u_node.y,
                        "x2": v_node.x, "y2": v_node.y,
                        "distance": dist,
                        "state": "traveling",
                        "node": v_id,
                        "load": curr_load,
                        "batch_id": batch["id"],
                        "info": f"Di chuyển tới {v_id}"
                    })
                    curr_t += travel_dur

                # Arrived at stop_to: pick items if any are located here
                picked_items = {}
                for oid in batch["orders"]:
                    order = orders_dict[oid]
                    for item_id, qty in order.items.items():
                        if item_id not in already_picked and products_dict[item_id].location == stop_to:
                            picked_items[item_id] = picked_items.get(item_id, 0) + qty

                if picked_items:
                    for it in picked_items:
                        already_picked.add(it)
                    stop_load = sum(products_dict[it].size * q for it, q in picked_items.items())
                    stop_pick_time = sum(products_dict[it].pick_minutes * q for it, q in picked_items.items())
                    stop_dur = op.location_minutes + stop_pick_time

                    segments.append({
                        "t_start": curr_t,
                        "t_end": curr_t + stop_dur,
                        "x1": nodes_dict[stop_to].x, "y1": nodes_dict[stop_to].y,
                        "x2": nodes_dict[stop_to].x, "y2": nodes_dict[stop_to].y,
                        "state": "picking",
                        "node": stop_to,
                        "load": curr_load + stop_load,
                        "batch_id": batch["id"],
                        "info": f"Lấy {sum(picked_items.values())} sản phẩm tại {stop_to}",
                        "pick_qty": sum(picked_items.values()),
                        "pick_load": stop_load,
                        "pick_items": picked_items
                    })
                    curr_t += stop_dur
                    curr_load += stop_load

            # 3. Batch completion at depot
            if abs(traveled_distance - batch["distance"]) > 1e-7:
                raise InputError(f"Batch {batch['id']} simulation distance disagrees with evaluator")
            if abs(curr_load - batch["load"]) > 1e-7:
                raise InputError(f"Batch {batch['id']} simulation load disagrees with evaluator")
            if abs(curr_t - batch["end"]) > 1e-7:
                raise InputError(f"Batch {batch['id']} simulation time disagrees with evaluator")
            end_t = curr_t
            segments.append({
                "t_start": curr_t,
                "t_end": end_t,
                "x1": depot_node.x, "y1": depot_node.y,
                "x2": depot_node.x, "y2": depot_node.y,
                "state": "unloading",
                "node": instance.depot,
                "load": curr_load,
                "batch_id": batch["id"],
                "info": f"Dỡ hàng ({batch['id']})"
            })

        pickers_data.append({
            "id": p_idx,
            "name": f"Nhân viên {p_idx}",
            "color": color,
            "batches_count": len(batches),
            "segments": segments
        })

    orders_info = []
    for o in result.get("orders", []):
        orders_info.append({
            "id": o["id"],
            "batch": o["batch"],
            "picker": o["picker"],
            "due": o["due"],
            "completion": o["completion"],
            "tardiness": o["tardiness"]
        })

    time_unit = unit_label(instance, "time")
    time_scale = time_scale_seconds(instance)

    payload = {
        "depot": {"id": instance.depot, "x": nodes_dict[instance.depot].x, "y": nodes_dict[instance.depot].y},
        "nodes": {n.id: {"x": n.x, "y": n.y} for n in instance.nodes},
        "edges": edges_data,
        "shelf_blocks": shelf_blocks,
        "bounds": {"min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y},
        "pickers": pickers_data,
        "orders": orders_info,
        "capacity": op.capacity,
        "capacity_unit": unit_label(instance, "capacity"),
        "speed": op.speed,
        "makespan": result["metrics"]["makespan"],
        "late_orders": result["metrics"]["late_orders"],
        "total_distance": result["metrics"]["distance"],
        "is_source_units": time_scale == 1.0,
        "time_unit": time_unit,
        "time_scale_seconds": time_scale
    }
    return payload


def render_simulation(instance, result, height=750):
    """Render a self-contained replay of the validated warehouse timeline."""
    data = build_simulation_data(instance, result)
    json_str = json.dumps(data, ensure_ascii=False)

    html_code = f"""
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{
    width: 100%;
    height: 100%;
    overflow: hidden;
    background: #0f172a;
    color: #f8fafc;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    user-select: none;
  }}
  .sim-container {{
    display: flex;
    flex-direction: column;
    height: 100%;
    padding: 10px;
    gap: 8px;
  }}
  /* Controls Bar */
  .controls-bar {{
    display: flex;
    flex-direction: column;
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 6px 10px;
    gap: 6px;
    flex-shrink: 0;
    min-width: 0;
  }}
  .control-row {{
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    flex-wrap: wrap;
    min-width: 0;
  }}
  .btn-group {{
    display: flex;
    align-items: center;
    gap: 5px;
    min-width: 0;
    flex-shrink: 0;
  }}
  .control-label, .playback-note {{
    font-size: 13px;
    line-height: 1.35;
    color: #cbd5e1;
  }}
  .control-label {{
    white-space: nowrap;
  }}
  .playback-note {{
    flex: 1 1 165px;
  }}
  .view-group {{
    margin-left: auto;
  }}
  button.sim-btn:focus-visible, .view-select:focus-visible, .timeline-slider:focus-visible {{
    outline: 2px solid #f8fafc;
    outline-offset: 3px;
  }}
  button.sim-btn {{
    background: #334155;
    color: #f8fafc;
    border: none;
    padding: 6px 9px;
    min-height: 32px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
    white-space: nowrap;
    display: flex;
    align-items: center;
    gap: 4px;
  }}
  button.sim-btn:hover {{
    background: #475569;
  }}
  button.sim-btn.primary {{
    background: #176b5b;
  }}
  button.sim-btn.primary:hover {{
    background: #1e8773;
  }}
  button.sim-btn.active {{
    background: #176b5b;
  }}
  .timeline-wrap {{
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1 1 350px;
    min-width: 0;
  }}
  .timeline-slider {{
    flex: 1;
    width: 0;
    min-width: 100px;
    -webkit-appearance: none;
    height: 6px;
    border-radius: 3px;
    background: #475569;
    outline: none;
    cursor: pointer;
  }}
  .timeline-slider::-webkit-slider-thumb {{
    -webkit-appearance: none;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: #38bdf8;
    cursor: pointer;
    box-shadow: 0 0 8px rgba(56, 189, 248, 0.7);
  }}
  .time-badge {{
    font-family: monospace;
    font-size: 13px;
    font-weight: bold;
    color: #38bdf8;
    background: #0f172a;
    padding: 5px 8px;
    border-radius: 5px;
    border: 1px solid #334155;
    min-width: 0;
    max-width: 100%;
    text-align: center;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex-shrink: 0;
    overflow-wrap: anywhere;
  }}
  .view-select {{
    background: #334155;
    color: #f8fafc;
    border: 1px solid #475569;
    padding: 5px 8px;
    border-radius: 6px;
    min-height: 32px;
    max-width: 180px;
    font-size: 13px;
    font-weight: 500;
    outline: none;
    cursor: pointer;
  }}
  /* Canvas Stage */
  .stage-wrap {{
    flex: 1;
    min-width: 0;
    min-height: 0;
    background: #182234;
    border: 1px solid #334155;
    border-radius: 10px;
    position: relative;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: grab;
  }}
  .stage-wrap:active {{
    cursor: grabbing;
  }}
  canvas#simCanvas {{
    display: block;
    width: 100%;
    height: 100%;
  }}
  /* Live HUD Cards */
  .hud-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 225px), 1fr));
    gap: 8px;
    max-height: 100px;
    overflow-y: auto;
    min-width: 0;
    flex-shrink: 0;
  }}
  .picker-card {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 7px 10px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 13px;
    line-height: 1.35;
    min-width: 0;
    overflow-wrap: anywhere;
  }}
  .picker-card.focused {{
    border-color: #38bdf8;
    box-shadow: 0 0 8px rgba(56, 189, 248, 0.3);
  }}
  .picker-card-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 4px 8px;
    font-weight: bold;
  }}
  .picker-dot {{
    width: 10px;
    height: 10px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 4px;
  }}
  .picker-status {{
    color: #94a3b8;
    white-space: normal;
    overflow-wrap: anywhere;
  }}
  .load-bar-wrap {{
    background: #334155;
    height: 5px;
    border-radius: 3px;
    overflow: hidden;
    position: relative;
  }}
  .load-bar-fill {{
    height: 100%;
    background: #38bdf8;
    border-radius: 3px;
    transition: width 0.1s ease;
  }}
  @media (max-width: 700px) {{
    .timeline-wrap {{ flex-basis: 100%; }}
    .playback-note {{ flex-basis: 100%; order: 3; }}
    .view-group {{ flex-wrap: wrap; }}
    .time-badge {{ max-width: 52%; }}
  }}
</style>
</head>
<body>

<div class="sim-container">
  <!-- Controls Bar -->
  <div class="controls-bar">
    <div class="control-row">
      <div class="btn-group">
        <button class="sim-btn" id="playBtn">⏸ Tạm dừng</button>
        <button class="sim-btn" id="resetBtn" title="Tua về đầu">↺ Về đầu</button>
      </div>
      <div class="timeline-wrap">
        <label class="control-label" for="timelineSlider">Đồng hồ</label>
        <input type="range" class="timeline-slider" id="timelineSlider" aria-label="Thời gian vận hành" min="0" max="100" step="0.05" value="0">
        <div class="time-badge" id="timeBadge">00:00:00 / 00:00:00</div>
      </div>
    </div>
    <div class="control-row">
      <div class="btn-group">
        <span class="control-label">Tốc độ phát</span>
        <button class="sim-btn speed-btn" data-speed="0.5" title="Phát chậm (khoảng 60 giây)">0.5x</button>
        <button class="sim-btn active speed-btn" data-speed="1" title="Phát toàn bộ lịch trong khoảng 30 giây; không phải thời gian thực">1x</button>
        <button class="sim-btn speed-btn" data-speed="2" title="Phát nhanh (khoảng 15 giây)">2x</button>
        <button class="sim-btn speed-btn" data-speed="5" title="Phát nhanh (khoảng 6 giây)">5x</button>
      </div>
      <span class="playback-note" title="Tốc độ phát chỉ thay đổi tốc độ xem; đồng hồ và lịch vận hành giữ nguyên.">1x: toàn lượt ≈ 30 giây</span>
      <div class="btn-group view-group">
        <button class="sim-btn" id="zoomInBtn" title="Phóng to" aria-label="Phóng to">🔍+</button>
        <button class="sim-btn" id="zoomOutBtn" title="Thu nhỏ" aria-label="Thu nhỏ">🔍-</button>
        <button class="sim-btn" id="zoomResetBtn" title="Vừa khung hình" aria-label="Vừa khung hình">⛶</button>
        <select class="view-select" id="viewSelect" title="Theo dõi nhân viên" aria-label="Theo dõi nhân viên">
          <option value="all">Tất cả nhân viên</option>
        </select>
      </div>
    </div>
  </div>

  <!-- Simulation Canvas -->
  <div class="stage-wrap" id="stageWrap">
    <canvas id="simCanvas"></canvas>
  </div>

  <!-- Live Multi-Agent HUD -->
  <div class="hud-grid" id="hudGrid"></div>
</div>

<script>
  const simData = {json_str};

  // State
  let isPlaying = true; // Auto-play by default so users see motion immediately
  let simTime = 0.0;
  let speedMultiplier = 1.0;
  let focusPicker = "all"; // "all" or picker id (1..N)
  let lastTimestamp = null;
  const timeUnit = simData.time_unit || "đơn vị thời gian";
  const timeScaleSeconds = Number.isFinite(simData.time_scale_seconds) ? simData.time_scale_seconds : null;
  const capacityUnit = simData.capacity_unit || "đơn vị tải";
  const makespan = Math.max(0.0, simData.makespan);

  function formatNumber(value) {{
    return Number(value.toPrecision(12)).toString();
  }}

  function formatLoad(value) {{
    return `Tải: ${{formatNumber(value)}} / ${{formatNumber(simData.capacity)}} ${{capacityUnit}}`;
  }}

  // Auto-scale base speed so the full simulation plays comfortably in ~30 seconds at 1x
  const baseRate = makespan / 30.0;

  // Zoom & Pan state
  let zoomFactor = 1.0;
  let panX = 0;
  let panY = 0;
  let isDragging = false;
  let dragStartX = 0;
  let dragStartY = 0;

  // Breadcrumbs history for smooth dynamic motion trail
  const pickerTrails = {{}};
  simData.pickers.forEach(p => {{ pickerTrails[p.id] = []; }});

  function clearTrails() {{
    simData.pickers.forEach(p => {{ pickerTrails[p.id].length = 0; }});
  }}

  // DOM elements
  const canvas = document.getElementById("simCanvas");
  const ctx = canvas.getContext("2d");
  const stageWrap = document.getElementById("stageWrap");
  const playBtn = document.getElementById("playBtn");
  const resetBtn = document.getElementById("resetBtn");
  const timelineSlider = document.getElementById("timelineSlider");
  const timeBadge = document.getElementById("timeBadge");
  const speedBtns = document.querySelectorAll(".speed-btn");
  const viewSelect = document.getElementById("viewSelect");
  const hudGrid = document.getElementById("hudGrid");
  const zoomInBtn = document.getElementById("zoomInBtn");
  const zoomOutBtn = document.getElementById("zoomOutBtn");
  const zoomResetBtn = document.getElementById("zoomResetBtn");

  // Init slider
  timelineSlider.max = makespan;
  // A fixed step rounds the end down when makespan is not a multiple of it.
  timelineSlider.step = "any";
  timelineSlider.value = 0;

  // Init options and HUD
  simData.pickers.forEach(p => {{
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = p.name;
    viewSelect.appendChild(opt);

    const card = document.createElement("div");
    card.className = "picker-card";
    card.id = `card-p${{p.id}}`;
    card.innerHTML = `
      <div class="picker-card-header">
        <span><span class="picker-dot" style="background: ${{p.color}}"></span>${{p.name}}</span>
        <span id="card-load-p${{p.id}}" style="color: #cbd5e1; font-weight: normal;"></span>
      </div>
      <div class="picker-status" id="card-status-p${{p.id}}">Sẵn sàng</div>
      <div class="load-bar-wrap">
        <div class="load-bar-fill" id="card-bar-p${{p.id}}" style="width: 0%; background: ${{p.color}}"></div>
      </div>
    `;
    card.querySelector(`#card-load-p${{p.id}}`).textContent = formatLoad(0);
    hudGrid.appendChild(card);
  }});

  // Dynamic Canvas synchronization (called every frame)
  function syncCanvasSize() {{
    const width = Math.max(1, stageWrap.clientWidth);
    const height = Math.max(1, stageWrap.clientHeight);
    const dpr = window.devicePixelRatio || 1;
    const targetW = Math.round(width * dpr);
    const targetH = Math.round(height * dpr);
    if (canvas.width !== targetW || canvas.height !== targetH) {{
      canvas.width = targetW;
      canvas.height = targetH;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }}
  }}
  window.addEventListener("resize", syncCanvasSize);
  syncCanvasSize();

  // Coordinate mapping with Zoom & Pan
  function getTransform() {{
    const w = Math.max(1, stageWrap.clientWidth);
    const h = Math.max(1, stageWrap.clientHeight);
    const b = simData.bounds;
    const margin = Math.min(40, w / 4, h / 4);

    const spanX = Math.max(1, b.max_x - b.min_x);
    const spanY = Math.max(1, b.max_y - b.min_y);
    const baseScaleX = (w - margin * 2) / spanX;
    const baseScaleY = (h - margin * 2) / spanY;
    const baseScale = Math.min(baseScaleX, baseScaleY);
    const scale = baseScale * zoomFactor;

    const baseOffsetX = (w - spanX * scale) / 2 - b.min_x * scale;
    const baseOffsetY = (h - spanY * scale) / 2 - b.min_y * scale;

    const finalOffsetX = baseOffsetX + panX;
    const finalOffsetY = baseOffsetY + panY;

    return {{
      toScreenX: (x) => x * scale + finalOffsetX,
      toScreenY: (y) => h - (y * scale + finalOffsetY),
      scale: scale,
      w: w,
      h: h
    }};
  }}

  // Event Listeners for Playback
  playBtn.addEventListener("click", () => {{
    if (simTime >= makespan) {{
      simTime = 0.0;
      clearTrails();
      timelineSlider.value = 0;
      isPlaying = true;
      playBtn.textContent = "⏸ Tạm dừng";
      playBtn.className = "sim-btn";
      return;
    }}
    isPlaying = !isPlaying;
    playBtn.textContent = isPlaying ? "⏸ Tạm dừng" : "▶ Tiếp tục";
    playBtn.className = isPlaying ? "sim-btn" : "sim-btn primary";
  }});

  resetBtn.addEventListener("click", () => {{
    simTime = 0.0;
    clearTrails();
    timelineSlider.value = 0;
    isPlaying = false;
    playBtn.textContent = "▶ Bắt đầu";
    playBtn.className = "sim-btn primary";
    updateHUD();
  }});

  timelineSlider.addEventListener("input", (e) => {{
    simTime = Math.min(makespan, Math.max(0, parseFloat(e.target.value)));
    if (makespan - simTime < 1e-9) simTime = makespan;
    clearTrails();
    updateHUD();
  }});

  speedBtns.forEach(btn => {{
    btn.addEventListener("click", () => {{
      speedBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      speedMultiplier = parseFloat(btn.dataset.speed);
    }});
  }});

  viewSelect.addEventListener("change", (e) => {{
    focusPicker = e.target.value;
    document.querySelectorAll(".picker-card").forEach(c => c.classList.remove("focused"));
    if (focusPicker !== "all") {{
      const focusedCard = document.getElementById(`card-p${{focusPicker}}`);
      if (focusedCard) {{
        focusedCard.classList.add("focused");
        focusedCard.scrollIntoView({{ block: "nearest", inline: "nearest" }});
      }}
    }} else {{
      hudGrid.scrollTop = 0;
    }}
  }});

  // Zoom & Pan Events
  zoomInBtn.addEventListener("click", () => {{ zoomFactor = Math.min(5.0, zoomFactor * 1.3); }});
  zoomOutBtn.addEventListener("click", () => {{ zoomFactor = Math.max(0.5, zoomFactor / 1.3); }});
  zoomResetBtn.addEventListener("click", () => {{ zoomFactor = 1.0; panX = 0; panY = 0; }});

  stageWrap.addEventListener("wheel", (e) => {{
    e.preventDefault();
    const zoomDelta = e.deltaY < 0 ? 1.15 : 0.85;
    zoomFactor = Math.max(0.4, Math.min(6.0, zoomFactor * zoomDelta));
  }}, {{ passive: false }});

  stageWrap.addEventListener("mousedown", (e) => {{
    if (e.button === 0) {{
      isDragging = true;
      dragStartX = e.clientX - panX;
      dragStartY = e.clientY - panY;
    }}
  }});

  window.addEventListener("mousemove", (e) => {{
    if (isDragging) {{
      panX = e.clientX - dragStartX;
      panY = e.clientY - dragStartY;
    }}
  }});

  window.addEventListener("mouseup", () => {{ isDragging = false; }});

  // Picker position resolver
  function getPickerState(picker, t) {{
    const segments = picker.segments;
    const depot = simData.depot;

    if (!segments || segments.length === 0) {{
      return {{ x: depot.x, y: depot.y, state: "idle", load: 0, info: "Đang chờ tại điểm xuất phát", pick_qty: 0, heading: 0, setup_pct: 0 }};
    }}

    // After last batch
    const lastSeg = segments[segments.length - 1];
    if (t >= lastSeg.t_end) {{
      return {{ x: lastSeg.x2, y: lastSeg.y2, state: "idle", load: 0, info: "Đã hoàn thành công việc", pick_qty: 0, heading: 0, setup_pct: 100 }};
    }}

    // Before first batch
    if (t <= segments[0].t_start) {{
      return {{ x: segments[0].x1, y: segments[0].y1, state: "idle", load: 0, info: "Sẵn sàng tại điểm xuất phát", pick_qty: 0, heading: 0, setup_pct: 0 }};
    }}

    // Find active segment
    for (let i = 0; i < segments.length; i++) {{
      const seg = segments[i];
      if (t >= seg.t_start && t <= seg.t_end) {{
        const span = seg.t_end - seg.t_start;
        const alpha = span > 0 ? Math.min(1, Math.max(0, (t - seg.t_start) / span)) : 1;
        const curX = seg.x1 + alpha * (seg.x2 - seg.x1);
        const curY = seg.y1 + alpha * (seg.y2 - seg.y1);
        const heading = Math.atan2(seg.y2 - seg.y1, seg.x2 - seg.x1);
        const setupPct = seg.state === "setup" ? Math.round(alpha * 100) : 0;
        return {{
          x: curX,
          y: curY,
          state: seg.state,
          load: seg.load,
          info: seg.state === "setup" ? `⚙️ Chuẩn bị xe (${{setupPct}}%)` : seg.info,
          pick_qty: seg.pick_qty || 0,
          batch_id: seg.batch_id,
          heading: heading,
          setup_pct: setupPct
        }};
      }}
      // Gap between segments
      if (i + 1 < segments.length && t > seg.t_end && t < segments[i + 1].t_start) {{
        return {{
          x: seg.x2,
          y: seg.y2,
          state: "idle",
          load: seg.load,
          info: "Đang chờ",
          pick_qty: 0,
          heading: 0,
          setup_pct: 0
        }};
      }}
    }}

    return {{ x: depot.x, y: depot.y, state: "idle", load: 0, info: "Đang chờ tại điểm xuất phát", pick_qty: 0, heading: 0, setup_pct: 0 }};
  }}

  // Unified clock formatting
  function formatClock(val) {{
    if (timeScaleSeconds === null) {{
      return `${{formatNumber(Math.max(0, val))}} ${{timeUnit}}`;
    }}
    const totalSec = Math.max(0, Math.round(val * timeScaleSeconds));
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;
    if (h > 0) {{
      return `${{h}} giờ ${{String(m).padStart(2, '0')}} phút ${{String(s).padStart(2, '0')}} giây`;
    }}
    return `${{m}} phút ${{String(s).padStart(2, '0')}} giây`;
  }}

  function formatTimeBadge(curVal, maxVal) {{
    if (timeScaleSeconds === null) {{
      return `⏱️ ${{formatNumber(curVal)}} / ${{formatNumber(maxVal)}} ${{timeUnit}}`;
    }}
    function compactClock(val) {{
      const totalSec = Math.max(0, Math.round(val * timeScaleSeconds));
      const h = Math.floor(totalSec / 3600);
      const m = Math.floor((totalSec % 3600) / 60);
      const s = totalSec % 60;
      return `${{String(h).padStart(2, '0')}}:${{String(m).padStart(2, '0')}}:${{String(s).padStart(2, '0')}}`;
    }}
    return `${{compactClock(curVal)}} / ${{compactClock(maxVal)}}`;
  }}

  // Update HUD
  function updateHUD() {{
    timeBadge.textContent = formatTimeBadge(simTime, makespan);
    timeBadge.title = `Thời gian vận hành: ${{formatClock(simTime)}} / ${{formatClock(makespan)}}`;
    timelineSlider.value = simTime;

    simData.pickers.forEach(p => {{
      const st = getPickerState(p, simTime);
      const statusEl = document.getElementById(`card-status-p${{p.id}}`);
      const loadEl = document.getElementById(`card-load-p${{p.id}}`);
      const barEl = document.getElementById(`card-bar-p${{p.id}}`);

      if (statusEl) statusEl.textContent = st.info;
      if (loadEl) loadEl.textContent = formatLoad(st.load);
      if (barEl) {{
        const pct = Math.min(100, (st.load / simData.capacity) * 100);
        barEl.style.width = `${{pct}}%`;
      }}
    }});
  }}

  // Main render loop
  function render(timestamp) {{
    syncCanvasSize();

    if (!lastTimestamp) lastTimestamp = timestamp;
    const dt = Math.min(0.1, (timestamp - lastTimestamp) / 1000); // capped to avoid jumps
    lastTimestamp = timestamp;

    if (isPlaying) {{
      const timeStep = dt * baseRate * speedMultiplier;
      simTime += timeStep;
      if (simTime >= makespan) {{
        simTime = makespan;
        isPlaying = false;
        playBtn.textContent = "↺ Xem lại";
        playBtn.className = "sim-btn primary";
      }}
      updateHUD();
    }}

    const T = getTransform();
    ctx.clearRect(0, 0, T.w, T.h);

    // 1. Draw Shelving Blocks (Racks)
    simData.shelf_blocks.forEach(block => {{
      const sx = T.toScreenX(block.x);
      const sy = T.toScreenY(block.y + block.h);
      const sw = block.w * T.scale;
      const sh = block.h * T.scale;

      ctx.fillStyle = "#1e293b";
      ctx.strokeStyle = "#334155";
      ctx.lineWidth = 1.2;

      ctx.beginPath();
      ctx.roundRect(sx, sy, sw, sh, Math.min(4, sw / 2));
      ctx.fill();
      ctx.stroke();

      // Inner rack shelf lines
      if (sh > 15 && sw > 6) {{
        ctx.strokeStyle = "#253347";
        ctx.lineWidth = 1;
        const steps = Math.min(6, Math.max(2, Math.floor(sh / 14)));
        for (let s = 1; s < steps; s++) {{
          const ly = sy + (sh / steps) * s;
          ctx.beginPath();
          ctx.moveTo(sx + 2, ly);
          ctx.lineTo(sx + sw - 2, ly);
          ctx.stroke();
        }}
      }}
    }});

    // 2. Draw Aisle Grid Lines (Edges)
    ctx.strokeStyle = "#334155";
    ctx.lineWidth = Math.max(1, Math.min(2.5, 30 * T.scale));
    simData.edges.forEach(e => {{
      const n1 = simData.nodes[e.source];
      const n2 = simData.nodes[e.target];
      if (n1 && n2) {{
        ctx.beginPath();
        ctx.moveTo(T.toScreenX(n1.x), T.toScreenY(n1.y));
        ctx.lineTo(T.toScreenX(n2.x), T.toScreenY(n2.y));
        ctx.stroke();
      }}
    }});

    // 3. Draw Nodes (Pick locations)
    const nodeR = Math.max(1.8, Math.min(3.5, 25 * T.scale));
    ctx.fillStyle = "#475569";
    Object.values(simData.nodes).forEach(n => {{
      ctx.beginPath();
      ctx.arc(T.toScreenX(n.x), T.toScreenY(n.y), nodeR, 0, Math.PI * 2);
      ctx.fill();
    }});

    // 4. Draw Depot
    const depot = simData.depot;
    const dsx = T.toScreenX(depot.x);
    const dsy = T.toScreenY(depot.y);
    const depotSize = Math.max(20, Math.min(30, 180 * T.scale));

    ctx.fillStyle = "#0284c7";
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.roundRect(dsx - depotSize / 2, dsy - depotSize / 2, depotSize, depotSize, 4);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "#ffffff";
    ctx.font = `bold ${{Math.max(10, Math.min(12, depotSize * 0.4))}}px sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("DEPOT", dsx, dsy);

    // 5. Calculate and draw pickers
    const aisleSpan = 8;
    const aisleScreenDist = aisleSpan * T.scale;
    const pickerRadius = Math.max(8, Math.min(13, aisleScreenDist * 0.75));
    const pickerStates = simData.pickers.map(p => ({{
      picker: p,
      state: getPickerState(p, simTime)
    }}));

    // Keep co-located markers distinct; a connector preserves their true position.
    const placed = [{{ x: dsx, y: dsy, radius: depotSize / 2 }}];
    const spacing = pickerRadius * 2 + 8;
    const inset = pickerRadius + 3;
    pickerStates.forEach(item => {{
      const anchorX = T.toScreenX(item.state.x);
      const anchorY = T.toScreenY(item.state.y);
      let marker = null;
      for (let ring = 0; ring <= pickerStates.length && !marker; ring++) {{
        const count = ring === 0 ? 1 : ring * 6;
        for (let slot = 0; slot < count; slot++) {{
          const angle = slot * Math.PI * 2 / count;
          const x = Math.max(inset, Math.min(T.w - inset, anchorX + Math.cos(angle) * spacing * ring));
          const y = Math.max(inset, Math.min(T.h - inset, anchorY + Math.sin(angle) * spacing * ring));
          if (placed.every(other => Math.hypot(x - other.x, y - other.y) >= pickerRadius + other.radius + 4)) {{
            marker = {{ x, y, radius: pickerRadius }};
            break;
          }}
        }}
      }}
      item.marker = marker || {{ x: anchorX, y: anchorY, radius: pickerRadius }};
      placed.push(item.marker);
    }});

    const statusBadges = [];
    function drawStatusBadge(text, item, preferAbove = false) {{
      const marker = item.marker;
      ctx.font = "bold 11px sans-serif";
      const w = Math.max(52, ctx.measureText(text).width + 12);
      const h = 20;
      const above = {{ x: marker.x - w / 2, y: marker.y - pickerRadius - h - 3 }};
      const right = {{ x: marker.x + pickerRadius + 3, y: marker.y - h / 2 }};
      const candidates = [preferAbove ? above : right, preferAbove ? right : above,
        {{ x: marker.x - pickerRadius - w - 3, y: marker.y - h / 2 }},
        {{ x: marker.x - w / 2, y: marker.y + pickerRadius + 3 }}];
      for (const rect of candidates) {{
        if (rect.x < 3 || rect.y < 3 || rect.x + w > T.w - 3 || rect.y + h > T.h - 3) continue;
        const markersToAvoid = focusPicker === "all" ? placed.filter(other => other !== marker) : [placed[0]];
        const coversMarker = markersToAvoid.some(other => {{
          const dx = other.x - Math.max(rect.x, Math.min(rect.x + w, other.x));
          const dy = other.y - Math.max(rect.y, Math.min(rect.y + h, other.y));
          return Math.hypot(dx, dy) < other.radius + 3;
        }});
        const coversBadge = statusBadges.some(other => rect.x < other.x + other.w + 3
          && rect.x + w + 3 > other.x && rect.y < other.y + other.h + 3 && rect.y + h + 3 > other.y);
        if (coversMarker || coversBadge) continue;
        ctx.fillStyle = item.picker.color;
        ctx.beginPath();
        ctx.roundRect(rect.x, rect.y, w, h, 3);
        ctx.fill();
        ctx.fillStyle = "#ffffff";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(text, rect.x + w / 2, rect.y + h / 2);
        statusBadges.push({{ ...rect, w, h }});
        return;
      }}
    }}

    pickerStates.forEach(item => {{
      const p = item.picker;
      const st = item.state;
      const isFocused = focusPicker === "all" || focusPicker == p.id;
      const alpha = isFocused ? 1.0 : 0.22;

      const sx = item.marker.x;
      const sy = item.marker.y;
      const anchorX = T.toScreenX(st.x);
      const anchorY = T.toScreenY(st.y);
      if (isFocused && Math.hypot(sx - anchorX, sy - anchorY) > 1) {{
        ctx.beginPath();
        ctx.moveTo(anchorX, anchorY);
        ctx.lineTo(sx, sy);
        ctx.strokeStyle = p.color;
        ctx.lineWidth = 1;
        ctx.globalAlpha = 0.45;
        ctx.stroke();
        ctx.globalAlpha = 1;
      }}

      // Breadcrumb history trail
      const trail = pickerTrails[p.id];
      if (st.state === "traveling") {{
        const previous = trail[trail.length - 1];
        if (!previous || previous.x !== st.x || previous.y !== st.y) {{
          trail.push({{ x: st.x, y: st.y, t: timestamp }});
        }}
        if (trail.length > 12) trail.shift();
      }} else {{
        if (trail.length > 0 && Math.random() < 0.2) trail.shift();
      }}

      // Draw faint motion trail
      if (trail.length > 1 && isFocused) {{
        ctx.beginPath();
        ctx.moveTo(T.toScreenX(trail[0].x), T.toScreenY(trail[0].y));
        for (let t_idx = 1; t_idx < trail.length; t_idx++) {{
          ctx.lineTo(T.toScreenX(trail[t_idx].x), T.toScreenY(trail[t_idx].y));
        }}
        ctx.strokeStyle = p.color;
        ctx.lineWidth = Math.max(1.5, pickerRadius * 0.4);
        ctx.globalAlpha = 0.35;
        ctx.stroke();
        ctx.globalAlpha = 1.0;
      }}

      // Setup Animation at Depot (Spinning preparation halo)
      if (st.state === "setup" && isFocused) {{
        const rot = (timestamp / 250) % (Math.PI * 2);
        ctx.save();
        ctx.translate(sx, sy);
        ctx.rotate(rot);
        ctx.beginPath();
        ctx.arc(0, 0, pickerRadius + 5, 0, Math.PI * 1.5);
        ctx.strokeStyle = p.color;
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.restore();

        drawStatusBadge(`Chuẩn bị ${{st.setup_pct}}%`, item, true);
      }}

      // Picking Ripple Pulse Effect
      if (st.state === "picking" && isFocused) {{
        const pulse = (Math.sin(timestamp / 120) + 1) / 2;
        const radius = pickerRadius + 2 + pulse * 14;
        ctx.beginPath();
        ctx.arc(sx, sy, radius, 0, Math.PI * 2);
        ctx.strokeStyle = p.color;
        ctx.lineWidth = 2.2;
        ctx.globalAlpha = 0.8 - pulse * 0.6;
        ctx.stroke();
        ctx.globalAlpha = 1.0;

        drawStatusBadge(`Lấy ${{st.pick_qty || 1}}`, item);
      }}

      // Unloading Effect
      if (st.state === "unloading" && isFocused) {{
        const pulse = (Math.sin(timestamp / 150) + 1) / 2;
        ctx.beginPath();
        ctx.arc(sx, sy, pickerRadius + 4 + pulse * 8, 0, Math.PI * 2);
        ctx.strokeStyle = "#38bdf8";
        ctx.lineWidth = 2;
        ctx.globalAlpha = 0.7 - pulse * 0.5;
        ctx.stroke();
        ctx.globalAlpha = 1.0;
      }}

      // Cart Body
      ctx.globalAlpha = alpha;
      ctx.fillStyle = p.color;
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = Math.max(1.2, pickerRadius * 0.2);

      ctx.beginPath();
      ctx.arc(sx, sy, pickerRadius, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      // Heading directional pointer when moving
      if (st.state === "traveling" && Math.hypot(Math.cos(st.heading), Math.sin(st.heading)) > 0.1) {{
        const hx = sx + Math.cos(st.heading) * pickerRadius;
        const hy = sy - Math.sin(st.heading) * pickerRadius;
        ctx.beginPath();
        ctx.arc(hx, hy, Math.max(2, pickerRadius * 0.3), 0, Math.PI * 2);
        ctx.fillStyle = "#ffffff";
        ctx.fill();
      }}

      // Picker Label (e.g. P1, P2)
      ctx.fillStyle = "#ffffff";
      ctx.font = `bold ${{Math.max(10, Math.min(12, pickerRadius * 0.95))}}px sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(`P${{p.id}}`, sx, sy);

      // Load Mini-Indicator
      if (st.load > 0) {{
        const loadPct = Math.min(1, st.load / simData.capacity);
        const barW = Math.max(16, pickerRadius * 2.2);
        const barH = 3.5;
        ctx.fillStyle = "#0f172a";
        const barY = sy - pickerRadius - 6 >= 3 ? sy - pickerRadius - 6 : sy + pickerRadius + 3;
        ctx.fillRect(sx - barW / 2, barY, barW, barH);
        ctx.fillStyle = "#38bdf8";
        ctx.fillRect(sx - barW / 2, barY, barW * loadPct, barH);
      }}

      ctx.globalAlpha = 1.0;
    }});

    requestAnimationFrame(render);
  }}

  // Initialize display and start the render loop
  updateHUD();
  requestAnimationFrame(render);
</script>
</body>
</html>
"""
    components.html(html_code, height=height, scrolling=False)
