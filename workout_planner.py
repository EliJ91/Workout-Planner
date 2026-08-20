from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_DIR = Path(__file__).resolve().parent
DATA_PATH = APP_DIR / "workout_data.json"
APP_VERSION = "1.1.11"
TODAY = date.today().isoformat()
PLATE_DENOMINATIONS = [45, 35, 25, 10, 5, 2.5]
DEFAULT_WEIGHT_OFFSET = "45"
NEW_EXERCISE_OFFSET = "0"

DEFAULT_ROUTINES = {
    "Push Day": [
        {"exercise": "Incline Barbell Press", "weight": "125", "reps": "3x8"},
        {"exercise": "Seated Shoulder Press", "weight": "67.5", "reps": "3x10"},
        {"exercise": "Cable Chest Fly", "weight": "40", "reps": "3x8"},
        {"exercise": "Cable Lateral Raise", "weight": "15", "reps": "3x8"},
        {"exercise": "Cable Tricep Pushdown", "weight": "45", "reps": "3x10"},
        {"exercise": "Overhead Cable Tricep Extension", "weight": "40", "reps": "2x15"},
    ],
    "Pull Day": [
        {"exercise": "Barbell Row", "weight": "100", "reps": "3x8"},
        {"exercise": "Lat Pulldown", "weight": "100", "reps": "3x6"},
        {"exercise": "Cable Row 1 Arm", "weight": "40", "reps": "3x8"},
        {"exercise": "Face Pulls", "weight": "40", "reps": "3x12"},
        {"exercise": "Preacher Curl", "weight": "30", "reps": "3x10"},
        {"exercise": "Hammer Curl 1 Arm", "weight": "15", "reps": "2x10"},
    ],
}

SEED_DATA = {
    "settings": {"always_on_top": False},
    "selected_routine": "Push Day",
    "routines": DEFAULT_ROUTINES,
    "routine_logs": [],
}


@dataclass
class ExercisePoint:
    date: str
    routine: str
    exercise: str
    weight: str
    reps: str
    weight_label: str = "Weight"
    reps_label: str = "Reps"

    @property
    def numeric_weight(self) -> float:
        try:
            return float(self.weight)
        except ValueError:
            return 0


def bool_from_data(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def format_weight(value: float | int | str) -> str:
    if value == "":
        return ""
    rounded = round(float(value), 1)
    return str(int(rounded)) if rounded.is_integer() else f"{rounded:.1f}"


def format_weight_text(value: float | int | str | None, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return format_weight(text)
    except ValueError:
        return text


def is_valid_weight(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    try:
        weight = float(text)
    except ValueError:
        return False
    if weight < 0:
        return False
    increments = weight / 2.5
    return abs(increments - round(increments)) <= 0.00001


def is_valid_offset(value: str) -> bool:
    text = value.strip()
    if not text:
        return True
    try:
        weight = float(text)
    except ValueError:
        return False
    if weight < 0:
        return False
    increments = weight / 2.5
    return abs(increments - round(increments)) <= 0.00001


def parse_reps_for_summary(value: str) -> tuple[int, float]:
    text = str(value).strip().lower().replace("×", "x").replace("–", "-").replace("—", "-")
    pattern = re.search(r"(\d+)\s*(?:x|sets?\s*x?)\s*(\d+)(?:\s*-\s*(\d+))?", text)
    if pattern:
        sets = int(pattern.group(1))
        low = int(pattern.group(2))
        high = int(pattern.group(3)) if pattern.group(3) else low
        return sets, (low + high) / 2
    single = re.search(r"\d+", text)
    if single:
        return 1, float(single.group(0))
    return 0, 0


def summarize_routine_log(log: dict) -> dict:
    total_sets = 0
    total_reps = 0.0
    total_weight = 0.0
    for item in log.get("exercises", []):
        try:
            weight = float(str(item.get("weight", "")).strip())
        except ValueError:
            weight = 0
        sets, reps = parse_reps_for_summary(str(item.get("reps", "")))
        if sets <= 0 or reps <= 0:
            continue
        total_sets += sets
        total_reps += sets * reps
        total_weight += weight * sets * reps
    average_reps = total_reps / total_sets if total_sets else 0
    return {
        "date": log.get("date", ""),
        "routine": log.get("routine", ""),
        "total_weight": total_weight,
        "total_sets": total_sets,
        "average_reps": average_reps,
    }


def format_whole_number(value: float | int) -> str:
    return str(int(round(float(value))))


def plate_counts_for_weight(value: str, offset: str = DEFAULT_WEIGHT_OFFSET) -> tuple[float, list[tuple[float, int]]]:
    try:
        weight = float(str(value).strip())
        offset_text = str(offset).strip()
        offset_weight = float(offset_text) if offset_text else 0
    except ValueError:
        return 0, [(denomination, 0) for denomination in PLATE_DENOMINATIONS]

    if offset_weight < 0:
        return 0, [(denomination, 0) for denomination in PLATE_DENOMINATIONS]

    rounded_total = math.floor(weight / 5) * 5
    side_weight = max((rounded_total - offset_weight) / 2, 0)
    remaining = side_weight
    counts = []
    for denomination in PLATE_DENOMINATIONS:
        count = int(remaining // denomination)
        counts.append((denomination, count))
        remaining = round(remaining - denomination * count, 2)
    return side_weight, counts


def place_on_parent_screen(parent: tk.Tk | tk.Toplevel, window: tk.Toplevel, width: int, height: int) -> None:
    parent.update_idletasks()
    x = parent.winfo_rootx() + max((parent.winfo_width() - width) // 2, 0)
    y = parent.winfo_rooty() + max((parent.winfo_height() - height) // 2, 0)
    window.geometry(f"{width}x{height}+{x}+{y}")


def layer_popup(parent: "WorkoutPlannerApp", window: tk.Toplevel) -> None:
    window.transient(parent)
    window.attributes("-topmost", bool(parent.store.settings.get("always_on_top", False)))
    window.lift()
    window.focus_force()


def make_barbell_icon() -> tk.PhotoImage:
    icon = tk.PhotoImage(width=32, height=32)
    black = "#000000"
    icon.put(black, to=(9, 14, 23, 18))
    icon.put(black, to=(7, 8, 10, 24))
    icon.put(black, to=(22, 8, 25, 24))
    icon.put(black, to=(4, 10, 7, 22))
    icon.put(black, to=(25, 10, 28, 22))
    icon.put(black, to=(2, 13, 4, 19))
    icon.put(black, to=(28, 13, 30, 19))
    return icon


class WorkoutStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            data = json.loads(json.dumps(SEED_DATA))
            self._normalize_routine_offsets(data)
            self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return data

        with self.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        data.setdefault("settings", {"always_on_top": False})
        data.setdefault("routines", self._routines_from_legacy_groups(data))
        self._normalize_routine_offsets(data)
        data.setdefault("selected_routine", data.get("selected_group", next(iter(data["routines"]))))
        data.setdefault("routine_logs", self._logs_from_legacy_sets(data))
        if data["selected_routine"] not in data["routines"]:
            data["selected_routine"] = next(iter(data["routines"]))
        return data

    @staticmethod
    def _normalize_routine_offsets(data: dict) -> None:
        for rows in data.get("routines", {}).values():
            for row in rows:
                row.setdefault("weight_offset", DEFAULT_WEIGHT_OFFSET)
                row.setdefault("track_pb", False)

    @staticmethod
    def _routines_from_legacy_groups(data: dict) -> dict[str, list[dict]]:
        groups = data.get("groups") or DEFAULT_ROUTINES
        routines = {}
        for group_name, rows in groups.items():
            routines[group_name] = []
            for row in rows:
                weight = row.get("weight", row.get("target_weight", ""))
                routines[group_name].append(
                    {
                        "exercise": row.get("exercise", "New Exercise"),
                        "weight": format_weight(weight) if weight != "" else "",
                        "reps": str(row.get("reps", row.get("target_reps", ""))),
                        "weight_offset": str(row.get("weight_offset", DEFAULT_WEIGHT_OFFSET)),
                        "track_pb": bool_from_data(row.get("track_pb", False)),
                    }
                )
        return routines or json.loads(json.dumps(DEFAULT_ROUTINES))

    @staticmethod
    def _logs_from_legacy_sets(data: dict) -> list[dict]:
        logs_by_key: dict[tuple[str, str], dict] = {}
        for item in data.get("sets", []):
            routine = item.get("routine", item.get("exercise_group", "Imported"))
            log_date = item.get("date", TODAY)
            key = (log_date, routine)
            log = logs_by_key.setdefault(key, {"date": log_date, "routine": routine, "exercises": [], "pb_entries": []})
            weight = item.get("weight", item.get("target_weight", ""))
            log["exercises"].append(
                {
                    "exercise": item.get("exercise", "Exercise"),
                    "weight": format_weight(weight) if weight != "" else "",
                    "reps": str(item.get("reps", item.get("target_reps", ""))),
                    "weight_offset": str(item.get("weight_offset", DEFAULT_WEIGHT_OFFSET)),
                    "track_pb": bool_from_data(item.get("track_pb", False)),
                }
            )
        return list(logs_by_key.values())

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    @property
    def settings(self) -> dict:
        return self.data.setdefault("settings", {"always_on_top": False})

    @property
    def routines(self) -> dict[str, list[dict]]:
        return self.data.setdefault("routines", json.loads(json.dumps(DEFAULT_ROUTINES)))

    @property
    def selected_routine(self) -> str:
        selected = self.data.get("selected_routine", next(iter(self.routines)))
        return selected if selected in self.routines else next(iter(self.routines))

    @property
    def routine_logs(self) -> list[dict]:
        return self.data.setdefault("routine_logs", [])

    def update_routine(self, name: str, exercises: list[dict]) -> None:
        self.routines[name] = exercises
        self.data["selected_routine"] = name
        self.save()

    def create_routine(self, name: str) -> None:
        self.routines[name] = [
            {"exercise": "New Exercise", "weight": "", "reps": "", "weight_offset": NEW_EXERCISE_OFFSET, "track_pb": False}
        ]
        self.data["selected_routine"] = name
        self.save()

    def delete_routine(self, name: str) -> None:
        self.routines.pop(name, None)
        self.data["selected_routine"] = next(iter(self.routines))
        self.save()

    def log_routine(self, routine: str, exercises: list[dict], pb_entries: list[dict] | None = None) -> None:
        self.routine_logs.append(
            {"date": TODAY, "routine": routine, "exercises": exercises, "pb_entries": pb_entries or []}
        )
        self.save()

    def delete_routine_log(self, index: int) -> None:
        if 0 <= index < len(self.routine_logs):
            self.routine_logs.pop(index)
            self.save()

    def delete_routine_logs(self, indices: list[int]) -> None:
        for index in sorted(set(indices), reverse=True):
            if 0 <= index < len(self.routine_logs):
                self.routine_logs.pop(index)
        self.save()

    def history_export_payload(self) -> dict:
        return {
            "app": "Workout Planner",
            "exported_on": TODAY,
            "routine_logs": json.loads(json.dumps(self.routine_logs)),
        }

    def import_history_payload(self, payload: dict | list) -> tuple[int, int]:
        if isinstance(payload, dict):
            incoming_logs = payload.get("routine_logs", payload.get("history", []))
        elif isinstance(payload, list):
            incoming_logs = payload
        else:
            return 0, 0

        existing_dates = {str(log.get("date", "")) for log in self.routine_logs}
        imported = 0
        skipped = 0
        for log in incoming_logs:
            if not isinstance(log, dict):
                skipped += 1
                continue
            log_date = str(log.get("date", "")).strip()
            if not log_date or log_date in existing_dates:
                skipped += 1
                continue
            self.routine_logs.append(
                {
                    "date": log_date,
                    "routine": str(log.get("routine", "")),
                    "exercises": log.get("exercises", []) if isinstance(log.get("exercises", []), list) else [],
                    "pb_entries": log.get("pb_entries", []) if isinstance(log.get("pb_entries", []), list) else [],
                }
            )
            existing_dates.add(log_date)
            imported += 1
        if imported:
            self.save()
        return imported, skipped

    def set_always_on_top(self, enabled: bool) -> None:
        self.settings["always_on_top"] = enabled
        self.save()


class RoundedButton(tk.Canvas):
    def __init__(
        self,
        master: tk.Widget,
        text: str,
        command,
        *,
        width: int = 108,
        height: int = 32,
        variant: str = "secondary",
    ) -> None:
        self.command = command
        self.normal = "#38bdf8" if variant == "primary" else "#1a2230"
        self.hover = "#0ea5e9" if variant == "primary" else "#253044"
        self.press = "#0284c7" if variant == "primary" else "#303b52"
        self.fg = "#081018" if variant == "primary" else "#eef5ff"
        self.width = width
        self.height = height
        super().__init__(
            master,
            width=width,
            height=height,
            background="#071120",
            highlightthickness=0,
            cursor="hand2",
        )
        self.text = text
        self._draw(self.normal)
        self.bind("<Enter>", lambda _event: self._draw(self.hover))
        self.bind("<Leave>", lambda _event: self._draw(self.normal))
        self.bind("<ButtonPress-1>", lambda _event: self._draw(self.press))
        self.bind("<ButtonRelease-1>", self._release)

    def _draw(self, fill: str) -> None:
        self.delete("all")
        w = self.width
        h = self.height
        radius = 12
        points = [
            radius,
            0,
            w - radius,
            0,
            w,
            0,
            w,
            radius,
            w,
            h - radius,
            w,
            h,
            w - radius,
            h,
            radius,
            h,
            0,
            h,
            0,
            h - radius,
            0,
            radius,
            0,
            0,
        ]
        self.create_polygon(points, smooth=True, fill=fill, outline="")
        self.create_text(w / 2, h / 2, text=self.text, fill=self.fg, font=("Segoe UI", 9, "bold"))

    def _release(self, event: tk.Event) -> None:
        self._draw(self.hover)
        if 0 <= event.x <= self.width and 0 <= event.y <= self.height:
            self.command()

    def set_width(self, width: int) -> None:
        width = max(1, int(width))
        if width == self.width:
            return
        self.width = width
        self.configure(width=width)
        self._draw(self.normal)


class HamburgerButton(tk.Canvas):
    def __init__(self, master: tk.Widget, command, *, size: int = 36) -> None:
        self.command = command
        self.size = size
        self.normal = "#1a2230"
        self.hover = "#253044"
        self.press = "#303b52"
        super().__init__(
            master,
            width=size,
            height=size,
            background="#071120",
            highlightthickness=0,
            cursor="hand2",
        )
        self._draw(self.normal)
        self.bind("<Enter>", lambda _event: self._draw(self.hover))
        self.bind("<Leave>", lambda _event: self._draw(self.normal))
        self.bind("<ButtonPress-1>", lambda _event: self._draw(self.press))
        self.bind("<ButtonRelease-1>", self._release)

    def _draw(self, fill: str) -> None:
        self.delete("all")
        s = self.size
        radius = 10
        points = [
            radius,
            0,
            s - radius,
            0,
            s,
            0,
            s,
            radius,
            s,
            s - radius,
            s,
            s,
            s - radius,
            s,
            radius,
            s,
            0,
            s,
            0,
            s - radius,
            0,
            radius,
            0,
            0,
        ]
        self.create_polygon(points, smooth=True, fill=fill, outline="")
        for y in (12, 18, 24):
            self.create_line(10, y, s - 10, y, fill="#eef5ff", width=2, capstyle=tk.ROUND)

    def _release(self, event: tk.Event) -> None:
        self._draw(self.hover)
        if 0 <= event.x <= self.size and 0 <= event.y <= self.size:
            self.command()


class TrendChart(tk.Canvas):
    def __init__(self, master: tk.Widget, **kwargs) -> None:
        super().__init__(
            master,
            background="#111722",
            highlightthickness=1,
            highlightbackground="#253044",
            **kwargs,
        )
        self.points: list[tuple[float, float, ExercisePoint]] = []
        self.bind("<Motion>", self._show_hover)
        self.bind("<Leave>", lambda _event: self.delete("tooltip"))

    def draw(self, points: list[ExercisePoint]) -> None:
        self.delete("all")
        self.points = []
        width = max(self.winfo_width(), 1)
        height = max(self.winfo_height(), 1)
        usable_points = [point for point in reversed(points) if point.numeric_weight > 0]
        values = [point.numeric_weight for point in usable_points]
        if len(values) < 2:
            self.create_text(
                width / 2,
                height / 2,
                text="Save this item twice to see a trend.",
                fill="#8ea0b8",
                font=("Segoe UI", 11),
                width=max(width - 36, 80),
            )
            return

        pad_x = min(48, max(24, int(width * 0.12)))
        pad_y = min(36, max(22, int(height * 0.16)))
        low = min(values) * 0.92
        high = max(values) * 1.08
        if high == low:
            high += 1

        plot_w = max(width - pad_x * 2, 1)
        plot_h = max(height - pad_y * 2, 1)
        for index in range(4):
            y = pad_y + plot_h * index / 3
            self.create_line(pad_x, y, width - pad_x, y, fill="#202a3a")

        def xy(index: int, value: float) -> tuple[float, float]:
            x = pad_x + plot_w * index / (len(values) - 1)
            y = pad_y + plot_h * (1 - (value - low) / (high - low))
            return x, y

        coords = [xy(index, value) for index, value in enumerate(values)]
        for start, end in zip(coords, coords[1:]):
            self.create_line(*start, *end, fill="#38bdf8", width=3, smooth=True)
        for coord, point in zip(coords, usable_points):
            x, y = coord
            self.create_oval(x - 4, y - 4, x + 4, y + 4, fill="#38bdf8", outline="")
            self.points.append((x, y, point))

        self.create_text(pad_x, 18, text=f"{format_weight(values[0])} lb", fill="#8ea0b8", anchor="w")
        self.create_text(width - pad_x, 18, text=f"{format_weight(values[-1])} lb", fill="#eef5ff", anchor="e")

    def _show_hover(self, event: tk.Event) -> None:
        self.delete("tooltip")
        for x, y, point in self.points:
            if abs(event.x - x) <= 8 and abs(event.y - y) <= 8:
                chart_width = max(self.winfo_width(), 1)
                chart_height = max(self.winfo_height(), 1)
                text_width = max(110, min(210, chart_width - 28))
                text_x = event.x + 12
                text_y = event.y - 54
                if text_x + text_width + 16 > chart_width:
                    text_x = max(8, chart_width - text_width - 16)
                if text_y < 8:
                    text_y = event.y + 12
                text_id = self.create_text(
                    text_x,
                    text_y,
                    text=f"{point.exercise}\n{point.weight_label}: {point.weight}\n{point.reps_label}: {point.reps}",
                    fill="#eef5ff",
                    font=("Segoe UI", 9),
                    anchor="nw",
                    width=text_width,
                    tags=("tooltip",),
                )
                bbox = self.bbox(text_id)
                if bbox:
                    dx = 0
                    dy = 0
                    if bbox[0] - 8 < 0:
                        dx = 8 - (bbox[0] - 8)
                    elif bbox[2] + 8 > chart_width:
                        dx = chart_width - 8 - (bbox[2] + 8)
                    if bbox[1] - 6 < 0:
                        dy = 6 - (bbox[1] - 6)
                    elif bbox[3] + 6 > chart_height:
                        dy = chart_height - 6 - (bbox[3] + 6)
                    if dx or dy:
                        self.move(text_id, dx, dy)
                        bbox = self.bbox(text_id)
                    if not bbox:
                        return
                    box_id = self.create_rectangle(
                        bbox[0] - 8,
                        bbox[1] - 6,
                        bbox[2] + 8,
                        bbox[3] + 6,
                        fill="#1a2230",
                        outline="#38bdf8",
                        tags=("tooltip",),
                    )
                    self.tag_lower(box_id, text_id)
                return


class PlateLoadChart(tk.Canvas):
    CHART_WIDTH = 150
    CHART_HEIGHT = 120
    PLATE_DIMENSIONS = {
        45: (18, 80),
        35: (16, 68),
        25: (14, 58),
        10: (11, 44),
        5: (9, 34),
        2.5: (8, 26),
    }
    PLATE_COLORS = ("#f2f0e8", "#a8b7c4")

    def __init__(self, master: tk.Widget, weight_var: tk.StringVar, offset_var: tk.StringVar, **kwargs) -> None:
        self.weight_var = weight_var
        self.offset_var = offset_var
        super().__init__(
            master,
            width=self.CHART_WIDTH,
            height=self.CHART_HEIGHT,
            background="#101a2a",
            highlightthickness=1,
            highlightbackground="#2b3a51",
            **kwargs,
        )
        self.weight_var.trace_add("write", lambda *_args: self.draw())
        self.offset_var.trace_add("write", lambda *_args: self.draw())
        self.draw()

    def draw(self) -> None:
        self.delete("all")
        side_weight, counts = plate_counts_for_weight(self.weight_var.get(), self.offset_var.get())
        self.create_rectangle(0, 0, self.CHART_WIDTH, self.CHART_HEIGHT, fill="#101a2a", outline="#2b3a51")
        self.create_text(
            10,
            11,
            text=f"Barbels: {format_weight(side_weight)}lb",
            fill="#9eb5dc",
            anchor="w",
            font=("Segoe UI", 8, "bold"),
        )

        center_y = 65
        plates: list[float] = []
        for denomination, count in counts:
            plates.extend([denomination] * count)
        plates.sort(reverse=True)

        shaft_width = 16
        stop_width = 7
        tail_width = 24
        if not plates:
            empty_width = shaft_width + stop_width + 52
            stop_x = int((self.CHART_WIDTH - empty_width) / 2 + shaft_width)
            self._draw_barbell(stop_x, stop_x + stop_width + 52, center_y)
            return

        plate_gap = 6
        stack_width = sum(self.PLATE_DIMENSIONS[plate][0] for plate in plates) + plate_gap * max(len(plates) - 1, 0)
        loaded_width = shaft_width + stop_width + stack_width + tail_width
        start_x = max(8, int((self.CHART_WIDTH - loaded_width) / 2))
        stop_x = start_x + shaft_width
        sleeve_start = stop_x + stop_width
        plate_x = sleeve_start
        sleeve_end = min(plate_x + stack_width + tail_width, self.CHART_WIDTH - 8)
        self._draw_barbell(stop_x, sleeve_end, center_y)

        x = plate_x
        for index, plate_weight in enumerate(plates):
            width, height = self.PLATE_DIMENSIONS[plate_weight]
            color = self.PLATE_COLORS[index % len(self.PLATE_COLORS)]
            self._draw_plate(x, center_y, width, height, color)
            self.create_text(
                x + width / 2,
                108,
                text=format_weight(plate_weight),
                fill=color,
                font=("Segoe UI", 8, "bold"),
            )
            x += width + plate_gap

    def _draw_barbell(self, stop_x: int, sleeve_end: int, center_y: int) -> None:
        shaft_start = stop_x - 16
        sleeve_start = stop_x + 7
        bar_grey = "#9aa7b0"
        self.create_rectangle(shaft_start, center_y - 2, stop_x, center_y + 2, fill=bar_grey, outline="")
        self.create_rectangle(stop_x, center_y - 14, stop_x + 7, center_y + 14, fill=bar_grey, outline="")
        self.create_rectangle(sleeve_start, center_y - 5, sleeve_end, center_y + 5, fill=bar_grey, outline="")

    def _draw_plate(self, x: int, center_y: int, width: int, height: int, color: str) -> None:
        top = center_y - height / 2
        bottom = center_y + height / 2
        outline = "#000000" if color == self.PLATE_COLORS[0] else "#020916"
        self.create_rectangle(x, top, x + width, bottom, fill=color, outline=outline)


class WorkoutPlannerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Workout Planner")
        self.app_icon = make_barbell_icon()
        self.iconphoto(True, self.app_icon)
        self.geometry("470x820")
        self.minsize(410, 680)

        self.store = WorkoutStore(DATA_PATH)
        self.routine_name = tk.StringVar(value=self.store.selected_routine)
        self.current_routine = self.routine_name.get()
        self.rows: list[dict[str, tk.StringVar]] = []
        self.plate_charts: list[PlateLoadChart] = []
        self.edit_mode = False
        self.edit_snapshot: list[dict] | None = None
        self.loading_rows = False
        self.autosave_job: str | None = None
        self.scroll_fade_job: str | None = None
        self.current_page: ttk.Frame | None = None

        self._configure_style()
        self._build_screen()
        self._load_routine_rows()
        self._apply_always_on_top()
        self.protocol("WM_DELETE_WINDOW", self._close_app)

    def _configure_style(self) -> None:
        self.bg = "#020916"
        self.panel = "#071120"
        self.input_bg = "#101a2a"
        self.card_bg = "#0d1727"
        self.text = "#eef5ff"
        self.muted = "#91a4c8"
        self.line = "#2b3a51"
        self.configure(background=self.bg)

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=self.bg)
        style.configure("Main.TFrame", background=self.panel)
        style.configure("Card.TFrame", background=self.card_bg)
        style.configure("TLabel", background=self.panel, foreground=self.text, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=self.card_bg, foreground=self.text, font=("Segoe UI", 10))
        style.configure("CardMuted.TLabel", background=self.card_bg, foreground=self.muted, font=("Segoe UI", 8, "bold"))
        style.configure("AppTitle.TLabel", background=self.panel, foreground=self.text, font=("Segoe UI", 20, "bold"))
        style.configure("Title.TLabel", background=self.panel, foreground=self.text, font=("Segoe UI", 30, "bold"))
        style.configure("Muted.TLabel", background=self.panel, foreground=self.muted, font=("Segoe UI", 11))
        style.configure("Head.TLabel", background=self.panel, foreground=self.muted, font=("Segoe UI", 9, "bold"))
        style.configure("TEntry", fieldbackground=self.input_bg, foreground=self.text, insertcolor=self.text)
        style.configure("TCheckbutton", background=self.panel, foreground=self.text, font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", self.panel)], foreground=[("active", self.text)])
        style.configure("Treeview", background=self.panel, fieldbackground=self.panel, foreground=self.text, rowheight=30)
        style.configure("Treeview.Heading", background=self.input_bg, foreground=self.text, font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#253044")])

    def _build_screen(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.main_page = ttk.Frame(self, style="Main.TFrame", padding=20)
        main = self.main_page
        main.grid(row=0, column=0, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)

        header = ttk.Frame(main, style="Main.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ttk.Label(header, text="Workout Planner", style="AppTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.menu_button = HamburgerButton(header, lambda: self._open_app_menu(self.menu_button), size=36)
        self.menu_button.grid(row=0, column=1, sticky="e")
        self.app_menu = tk.Menu(
            self,
            tearoff=False,
            background=self.input_bg,
            foreground=self.text,
            activebackground="#253044",
            activeforeground="#eef5ff",
            disabledforeground=self.muted,
        )
        self._refresh_app_menu()

        controls = ttk.Frame(main, style="Main.TFrame")
        controls.grid(row=1, column=0, sticky="ew", pady=(14, 14))
        controls.grid_columnconfigure(0, weight=1)
        ttk.Label(controls, text="ROUTINE", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        self.routine_button = tk.Menubutton(
            controls,
            textvariable=self.routine_name,
            background=self.input_bg,
            foreground="#38bdf8",
            activebackground="#253044",
            activeforeground="#38bdf8",
            relief="flat",
            anchor="w",
            padx=10,
            height=1,
            font=("Segoe UI", 9),
            cursor="hand2",
        )
        self.routine_button.grid(row=1, column=0, sticky="ew", pady=(8, 0), ipady=3)
        self.routine_menu = tk.Menu(
            self.routine_button,
            tearoff=False,
            background=self.input_bg,
            foreground="#38bdf8",
            activebackground="#253044",
            activeforeground="#eef5ff",
        )
        self.routine_menu.bind("<Button-3>", self._delete_routine_from_menu)
        self.routine_button.configure(menu=self.routine_menu)
        self.delete_menu = tk.Menu(
            self,
            tearoff=False,
            background=self.input_bg,
            foreground="#fda4af",
            activebackground="#4a1f2a",
            activeforeground="#fecdd3",
        )
        self._rebuild_routine_menu()

        self.list_canvas = tk.Canvas(main, background=self.panel, highlightthickness=0)
        self.list_canvas.grid(row=2, column=0, sticky="nsew")
        self.scroll_indicator = tk.Canvas(main, width=9, background=self.panel, highlightthickness=0, borderwidth=0)
        self.scroll_indicator.grid(row=2, column=0, sticky="nse", padx=(0, 2))
        self.scroll_indicator.grid_remove()
        self.table = ttk.Frame(self.list_canvas, style="Main.TFrame")
        self.table.grid_columnconfigure(0, weight=1)
        self.list_window = self.list_canvas.create_window((0, 0), window=self.table, anchor="nw")
        self.table.bind("<Configure>", self._update_scroll_region)
        self.list_canvas.bind("<Configure>", self._fit_list_width)
        self._bind_list_drag(self.list_canvas)
        self._bind_list_drag(self.table)

        actions = ttk.Frame(main, style="Main.TFrame")
        actions.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        actions.grid_columnconfigure(0, weight=1)
        self.add_button_slot = ttk.Frame(actions, style="Main.TFrame")
        self.add_button_slot.grid(row=0, column=0, sticky="w")
        self.save_button = RoundedButton(actions, "Save Workout", self._save_button_pressed, width=430, height=44, variant="primary")
        self.save_button.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        actions.bind("<Configure>", self._fit_save_button)
        self.after_idle(self._resize_save_button)

    def _update_scroll_region(self, _event: tk.Event) -> None:
        self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all"))

    def _fit_list_width(self, event: tk.Event) -> None:
        self.list_canvas.itemconfigure(self.list_window, width=event.width)
        self._resize_save_button(event.width)

    def _fit_save_button(self, event: tk.Event) -> None:
        self._resize_save_button(event.width)

    def _resize_save_button(self, width: int | None = None) -> None:
        if not hasattr(self, "save_button"):
            return
        if width is None or width <= 1:
            width = self.list_canvas.winfo_width() if hasattr(self, "list_canvas") else 1
        if width <= 1:
            width = self.winfo_width() - 40
        if width <= 1:
            width = 430
        self.save_button.set_width(width)

    def _refresh_app_menu(self) -> None:
        self.app_menu.delete(0, tk.END)
        self.app_menu.add_command(label="Home", command=self._show_main_page)
        self.app_menu.add_command(label="Cancel" if self.edit_mode else "Edit Routine", command=self._toggle_edit_mode_from_menu)
        self.app_menu.add_command(label="New Routine", command=self._open_new_routine)
        self.app_menu.add_separator()
        self.app_menu.add_command(label="History", command=self._open_history_window)
        self.app_menu.add_command(label="Data", command=self._open_data_window)
        self.app_menu.add_command(label="Settings", command=self._open_settings)
        self.app_menu.add_separator()
        self.app_menu.add_command(label=f"Version {APP_VERSION}", state="disabled")

    def _open_app_menu(self, source: tk.Widget) -> None:
        self._refresh_app_menu()
        x = source.winfo_rootx()
        y = source.winfo_rooty() + source.winfo_height() + 4
        try:
            self.app_menu.tk_popup(x, y)
        finally:
            self.app_menu.grab_release()

    def _open_page(self, title: str) -> ttk.Frame:
        self._flush_autosave()
        if self.current_page is not None:
            self.current_page.destroy()
            self.current_page = None
        self.main_page.grid_remove()

        page = ttk.Frame(self, style="Main.TFrame", padding=20)
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        self.current_page = page

        header = ttk.Frame(page, style="Main.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ttk.Label(header, text=title, style="AppTitle.TLabel").grid(row=0, column=0, sticky="w")
        page_menu_button = HamburgerButton(header, lambda: self._open_app_menu(page_menu_button), size=36)
        page_menu_button.grid(row=0, column=1, sticky="e")

        body = ttk.Frame(page, style="Main.TFrame")
        body.grid(row=1, column=0, sticky="nsew", pady=(18, 0))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        return body

    def _show_main_page(self) -> None:
        if self.current_page is not None:
            self.current_page.destroy()
            self.current_page = None
        self.main_page.grid()
        self._rebuild_routine_menu()
        self._load_routine_rows()

    def _toggle_edit_mode_from_menu(self) -> None:
        self._show_main_page()
        self._toggle_edit_mode()

    def _pointer_y_in_list(self, event: tk.Event) -> int:
        return event.y_root - self.list_canvas.winfo_rooty()

    def _start_list_drag(self, event: tk.Event) -> None:
        self.list_canvas.scan_mark(0, self._pointer_y_in_list(event))

    def _drag_list(self, event: tk.Event) -> None:
        self.list_canvas.scan_dragto(0, self._pointer_y_in_list(event), gain=1)
        self._show_scroll_indicator()

    def _wheel_list(self, event: tk.Event) -> None:
        self.list_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self._show_scroll_indicator()

    def _show_scroll_indicator(self) -> None:
        first, last = self.list_canvas.yview()
        if last - first >= 0.999:
            return
        if self.scroll_fade_job is not None:
            self.after_cancel(self.scroll_fade_job)
            self.scroll_fade_job = None
        self.scroll_indicator.grid()
        self.scroll_indicator.tk.call("raise", self.scroll_indicator._w)
        self._draw_scroll_indicator("#38bdf8")
        self.scroll_fade_job = self.after(260, lambda: self._fade_scroll_indicator(0))

    def _fade_scroll_indicator(self, step: int) -> None:
        fade_colors = ("#2f9fd1", "#287fa9", "#205f80", "#183f57", "#10283a")
        if step >= len(fade_colors):
            self.scroll_indicator.delete("all")
            self.scroll_indicator.grid_remove()
            self.scroll_fade_job = None
            return
        self._draw_scroll_indicator(fade_colors[step])
        self.scroll_fade_job = self.after(45, lambda: self._fade_scroll_indicator(step + 1))

    def _draw_scroll_indicator(self, color: str) -> None:
        height = max(self.list_canvas.winfo_height(), 1)
        self.scroll_indicator.configure(height=height)
        self.scroll_indicator.delete("all")
        first, last = self.list_canvas.yview()
        pad = 8
        usable_height = max(height - pad * 2, 1)
        top = pad + int(first * usable_height)
        bottom = pad + int(last * usable_height)
        min_thumb = min(30, usable_height)
        if bottom - top < min_thumb:
            thumb_center = (top + bottom) // 2
            top = max(pad, thumb_center - min_thumb // 2)
            bottom = min(height - pad, top + min_thumb)
            top = max(pad, bottom - min_thumb)
        self.scroll_indicator.create_line(5, top, 5, bottom, fill=color, width=5, capstyle=tk.ROUND)

    def _bind_list_drag(self, widget: tk.Widget) -> None:
        if isinstance(widget, (tk.Entry, ttk.Entry, tk.Button, tk.Menubutton, RoundedButton)):
            return
        widget.bind("<ButtonPress-1>", self._start_list_drag, add="+")
        widget.bind("<B1-Motion>", self._drag_list, add="+")
        widget.bind("<MouseWheel>", self._wheel_list, add="+")
        for child in widget.winfo_children():
            self._bind_list_drag(child)

    def _rebuild_routine_menu(self) -> None:
        self.routine_menu.delete(0, tk.END)
        for routine in self.store.routines:
            self.routine_menu.add_command(label=routine, command=lambda name=routine: self._select_routine(name))

    def _select_routine(self, routine: str) -> None:
        if routine == self.current_routine:
            return
        self._flush_autosave()
        self._save_current_routine()
        self.routine_name.set(routine)
        self.current_routine = routine
        self.edit_mode = False
        self.edit_snapshot = None
        self._load_routine_rows()

    def _delete_routine_from_menu(self, event: tk.Event) -> None:
        index = self.routine_menu.index(f"@{event.y}")
        if index is None:
            return
        routine = self.routine_menu.entrycget(index, "label")
        self.delete_menu.delete(0, tk.END)
        self.delete_menu.add_command(label=f"Delete {routine}", command=lambda name=routine: self._delete_routine(name))
        try:
            self.delete_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.delete_menu.grab_release()

    def _delete_routine(self, routine: str) -> None:
        if len(self.store.routines) <= 1:
            messagebox.showinfo("Keep one routine", "You need at least one routine.", parent=self)
            return
        if not messagebox.askyesno("Delete routine", f"Delete {routine}?", parent=self):
            return
        self.store.delete_routine(routine)
        self.routine_name.set(self.store.selected_routine)
        self.current_routine = self.routine_name.get()
        self.edit_mode = False
        self.edit_snapshot = None
        self._rebuild_routine_menu()
        self._load_routine_rows()

    def _load_routine_rows(self) -> None:
        self.loading_rows = True
        for widget in self.table.grid_slaves():
            widget.destroy()

        self.rows = []
        self.plate_charts = []
        for index, exercise in enumerate(self.store.routines[self.current_routine], start=1):
            offset_value = exercise.get("weight_offset", DEFAULT_WEIGHT_OFFSET)
            row = {
                "exercise": tk.StringVar(value=exercise.get("exercise", "")),
                "weight": tk.StringVar(value=format_weight_text(exercise.get("weight", ""))),
                "reps": tk.StringVar(value=str(exercise.get("reps", ""))),
                "weight_offset": tk.StringVar(value=format_weight_text(offset_value, NEW_EXERCISE_OFFSET)),
                "track_pb": tk.BooleanVar(value=bool_from_data(exercise.get("track_pb", False))),
            }
            self.rows.append(row)
            for var in row.values():
                var.trace_add("write", lambda *_args: self._schedule_autosave())
            card = tk.Frame(
                self.table,
                background=self.card_bg,
                highlightbackground=self.line,
                highlightthickness=1,
                padx=14,
                pady=14,
            )
            card.grid(row=index, column=0, sticky="ew", padx=2, pady=8)
            card.grid_columnconfigure(0, weight=0)
            card.grid_columnconfigure(1, weight=1)
            chart = PlateLoadChart(card, row["weight"], row["weight_offset"])
            self.plate_charts.append(chart)
            chart.grid(row=0, column=0, rowspan=6, sticky="n", padx=(0, 14))
            detail = tk.Frame(card, background=self.card_bg)
            detail.grid(row=0, column=1, rowspan=6, sticky="nsew")
            detail.grid_columnconfigure(0, weight=1)
            detail.grid_columnconfigure(1, weight=1)
            if self.edit_mode:
                edit_actions = tk.Frame(detail, background=self.card_bg)
                edit_actions.grid(row=0, column=1, sticky="e")
                tk.Button(
                    edit_actions,
                    text="X",
                    command=lambda selected=row: self._delete_exercise(selected),
                    background="#2a1820",
                    foreground="#fda4af",
                    activebackground="#4a1f2a",
                    activeforeground="#fecdd3",
                    borderwidth=0,
                    highlightthickness=0,
                    width=2,
                    cursor="hand2",
                    font=("Segoe UI", 8, "bold"),
                ).pack(side="left", padx=(0, 6))
                self._pb_button(edit_actions, row).pack(side="left")
                self._entry(detail, row["exercise"]).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 12))
                ttk.Label(detail, text="WEIGHT", style="CardMuted.TLabel").grid(row=2, column=0, sticky="w")
                ttk.Label(detail, text="REPS", style="CardMuted.TLabel").grid(row=2, column=1, sticky="w", padx=(10, 0))
                self._entry(detail, row["weight"], width=8).grid(row=3, column=0, sticky="ew", pady=(4, 0))
                self._entry(detail, row["reps"], width=8).grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=(4, 0))
                ttk.Label(detail, text="SET WEIGHT OFFSET", style="CardMuted.TLabel").grid(
                    row=4, column=0, columnspan=2, sticky="w", pady=(10, 0)
                )
                self._entry(detail, row["weight_offset"]).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))
            else:
                card_header = tk.Frame(detail, background=self.card_bg)
                card_header.grid(row=0, column=0, columnspan=2, sticky="ew")
                card_header.grid_columnconfigure(0, weight=1)
                title = tk.Label(
                    card_header,
                    textvariable=row["exercise"],
                    background=self.card_bg,
                    foreground=self.text,
                    font=("Segoe UI", 13, "bold"),
                    justify="left",
                    anchor="w",
                    wraplength=180,
                )
                title.grid(row=0, column=0, sticky="ew", padx=(0, 8))
                card_header.bind("<Configure>", lambda event, label=title: label.configure(wraplength=max(event.width - 56, 120)))
                self._pb_button(card_header, row).grid(row=0, column=1, sticky="ne")
                ttk.Label(detail, text="WEIGHT", style="CardMuted.TLabel").grid(row=1, column=0, sticky="w", pady=(18, 0))
                ttk.Label(detail, text="REPS", style="CardMuted.TLabel").grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(18, 0))
                if row["track_pb"].get():
                    self._entry(detail, row["weight"], width=8).grid(row=2, column=0, sticky="ew", pady=(5, 0))
                    self._entry(detail, row["reps"], width=8).grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=(5, 0))
                else:
                    self._value_box(detail, row["weight"], suffix="lbs").grid(row=2, column=0, sticky="ew", pady=(5, 0))
                    self._value_box(detail, row["reps"]).grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=(5, 0))
            self._bind_list_drag(card)

        for widget in self.add_button_slot.winfo_children():
            widget.destroy()
        if self.edit_mode:
            self.add_button_slot.grid()
            RoundedButton(self.add_button_slot, "Add Exercise", self._add_exercise, width=118).pack()
        else:
            self.add_button_slot.grid_remove()
        self._refresh_app_menu()
        self.save_button.text = "Save Changes" if self.edit_mode else "Save Workout"
        self.save_button._draw(self.save_button.normal)
        self.loading_rows = False
        self._redraw_plate_charts()

    def _entry(self, parent: tk.Widget, variable: tk.StringVar, width: int | None = None) -> ttk.Entry:
        entry = ttk.Entry(parent, textvariable=variable, justify="center")
        if width:
            entry.configure(width=width)
        return entry

    def _value_box(self, parent: tk.Widget, variable: tk.StringVar, suffix: str = "") -> tk.Frame:
        box = tk.Frame(parent, background="#121f32", highlightbackground=self.line, highlightthickness=1, padx=10, pady=6)
        text = tk.Label(box, textvariable=variable, background="#121f32", foreground=self.text, font=("Segoe UI", 13, "bold"))
        text.pack(side="left")
        if suffix:
            tk.Label(box, text=suffix, background="#121f32", foreground=self.muted, font=("Segoe UI", 9)).pack(side="left", padx=(6, 0))
        return box

    def _pb_button(self, parent: tk.Widget, row: dict) -> tk.Button:
        active = bool(row["track_pb"].get())
        return tk.Button(
            parent,
            text="PB",
            command=lambda selected=row: self._toggle_pb_tracking(selected),
            background="#dc2626" if active else "#3b1014",
            foreground="#ffffff" if active else "#fca5a5",
            activebackground="#ef4444",
            activeforeground="#ffffff",
            borderwidth=0,
            highlightthickness=0,
            padx=10,
            pady=3,
            cursor="hand2",
            font=("Segoe UI", 8, "bold"),
        )

    def _toggle_pb_tracking(self, row: dict) -> None:
        row["track_pb"].set(not bool(row["track_pb"].get()))
        self._save_current_routine(validate=False)
        self._load_routine_rows()

    def _redraw_plate_charts(self) -> None:
        for chart in self.plate_charts:
            if chart.winfo_exists():
                chart.draw()

    def _toggle_edit_mode(self) -> None:
        self._flush_autosave()
        if self.edit_mode:
            if self.edit_snapshot is not None:
                self.store.update_routine(self.current_routine, self.edit_snapshot)
            self.edit_mode = False
            self.edit_snapshot = None
        else:
            self.edit_snapshot = json.loads(json.dumps(self.store.routines[self.current_routine]))
            self.edit_mode = True
        self._load_routine_rows()

    def _add_exercise(self) -> None:
        self.rows.append(
            {
                "exercise": tk.StringVar(value="New Exercise"),
                "weight": tk.StringVar(value=""),
                "reps": tk.StringVar(value=""),
                "weight_offset": tk.StringVar(value=NEW_EXERCISE_OFFSET),
                "track_pb": tk.BooleanVar(value=False),
            }
        )
        self._save_current_routine()
        self._load_routine_rows()

    def _delete_exercise(self, row_to_delete: dict[str, tk.StringVar]) -> None:
        if len(self.rows) <= 1:
            messagebox.showinfo("Keep one exercise", "Each routine needs at least one exercise.", parent=self)
            return
        self.rows = [row for row in self.rows if row is not row_to_delete]
        self._save_current_routine()
        self._load_routine_rows()

    def _open_new_routine(self) -> None:
        body = self._open_page("New Routine")
        body.grid_rowconfigure(3, weight=1)
        routine_name = tk.StringVar()
        status = tk.StringVar()

        ttk.Label(body, text="ROUTINE NAME", style="Head.TLabel").grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(body, textvariable=routine_name)
        entry.grid(row=1, column=0, sticky="ew", pady=(8, 10), ipady=4)
        ttk.Label(body, textvariable=status, style="Muted.TLabel").grid(row=2, column=0, sticky="w")

        def create() -> None:
            routine = routine_name.get().strip()
            if not routine:
                status.set("Enter a routine name.")
                return
            if routine in self.store.routines:
                status.set("That routine already exists.")
                return
            self.create_routine(routine)
            self._show_main_page()

        RoundedButton(body, "Create Routine", create, width=160, height=38, variant="primary").grid(row=4, column=0, sticky="e")
        entry.bind("<Return>", lambda _event: create())
        entry.focus_set()

    def create_routine(self, routine: str) -> None:
        routine = routine.strip()
        if not routine:
            messagebox.showerror("Check routine", "Enter a routine name.", parent=self)
            return
        if routine in self.store.routines:
            messagebox.showerror("Check routine", "That routine already exists.", parent=self)
            return
        self._flush_autosave()
        self._save_current_routine()
        self.store.create_routine(routine)
        self.routine_name.set(routine)
        self.current_routine = routine
        self.edit_mode = True
        self.edit_snapshot = json.loads(json.dumps(self.store.routines[self.current_routine]))
        self._rebuild_routine_menu()
        self._load_routine_rows()

    def _schedule_autosave(self) -> None:
        if self.loading_rows:
            return
        self._redraw_plate_charts()
        if self.autosave_job is not None:
            self.after_cancel(self.autosave_job)
        self.autosave_job = self.after(500, self._flush_autosave)

    def _flush_autosave(self) -> None:
        if self.autosave_job is not None:
            self.after_cancel(self.autosave_job)
            self.autosave_job = None
        if self.rows:
            self._save_current_routine(validate=False)
        self._redraw_plate_charts()

    def _save_current_routine(self, validate: bool = False) -> bool:
        if not self.rows:
            return False
        exercises = []
        for row in self.rows:
            exercise = row["exercise"].get().strip()
            weight = row["weight"].get().strip()
            reps = row["reps"].get().strip()
            offset = row["weight_offset"].get().strip() or NEW_EXERCISE_OFFSET
            if validate and (not exercise or not reps or not is_valid_weight(weight) or not is_valid_offset(offset)):
                messagebox.showerror(
                    "Check routine",
                    "Each exercise needs a name, reps, a weight in 2.5 lb increments, and an offset of 0 or a 2.5 lb increment.",
                    parent=self,
                )
                return False
            exercises.append(
                {
                    "exercise": exercise or "New Exercise",
                    "weight": format_weight(weight) if weight and is_valid_weight(weight) else weight,
                    "reps": reps,
                    "weight_offset": format_weight(offset) if is_valid_offset(offset) else offset,
                    "track_pb": bool(row["track_pb"].get()),
                }
            )
        self.store.update_routine(self.current_routine, exercises)
        self._redraw_plate_charts()
        return True

    def _save_button_pressed(self) -> None:
        if self.edit_mode:
            if self._save_current_routine(validate=True):
                self.edit_mode = False
                self.edit_snapshot = None
                self._load_routine_rows()
                self._show_confirmation("Changes saved", f"{self.current_routine} was updated.")
            return

        if not self._save_current_routine(validate=True):
            return
        if not messagebox.askyesno(
            "Save workout",
            f"Save {self.current_routine} for {TODAY}?",
            parent=self,
        ):
            return
        self.store.log_routine(self.current_routine, self._rows_as_exercises(), self._pb_entries_as_exercises())
        self._show_confirmation("Workout saved", f"{self.current_routine} was saved for {TODAY}.")

    def _show_confirmation(self, title: str, message: str) -> None:
        messagebox.showinfo(title, message, parent=self)
        self._redraw_plate_charts()

    def _rows_as_exercises(self) -> list[dict]:
        return [
            {
                "exercise": row["exercise"].get().strip(),
                "weight": format_weight(row["weight"].get().strip()),
                "reps": row["reps"].get().strip(),
                "weight_offset": format_weight(row["weight_offset"].get().strip() or NEW_EXERCISE_OFFSET),
                "track_pb": bool(row["track_pb"].get()),
            }
            for row in self.rows
        ]

    def _pb_entries_as_exercises(self) -> list[dict]:
        return [
            {
                "exercise": row["exercise"].get().strip(),
                "weight": format_weight(row["weight"].get().strip()),
                "reps": row["reps"].get().strip(),
            }
            for row in self.rows
            if bool(row["track_pb"].get())
        ]

    def _close_app(self) -> None:
        self._flush_autosave()
        self.destroy()

    def _apply_always_on_top(self) -> None:
        enabled = bool(self.store.settings.get("always_on_top", False))
        self.attributes("-topmost", enabled)
        for child in self.winfo_children():
            if isinstance(child, tk.Toplevel):
                child.attributes("-topmost", enabled)
                child.lift()
        self._redraw_plate_charts()

    def _exercise_points(self) -> list[ExercisePoint]:
        points = []
        for log in self.store.routine_logs:
            for item in log.get("exercises", []):
                points.append(
                    ExercisePoint(
                        date=log.get("date", ""),
                        routine=log.get("routine", ""),
                        exercise=item.get("exercise", ""),
                        weight=str(item.get("weight", "")),
                        reps=str(item.get("reps", "")),
                    )
                )
        return sorted(points, key=lambda point: point.date, reverse=True)

    def _pb_points(self) -> list[ExercisePoint]:
        points = []
        for log in self.store.routine_logs:
            entries = log.get("pb_entries", [])
            if not isinstance(entries, list):
                entries = []
            if not entries:
                entries = [item for item in log.get("exercises", []) if bool_from_data(item.get("track_pb", False))]
            for item in entries:
                exercise = str(item.get("exercise", "")).strip()
                if not exercise:
                    continue
                points.append(
                    ExercisePoint(
                        date=log.get("date", ""),
                        routine=log.get("routine", ""),
                        exercise=exercise,
                        weight=str(item.get("weight", "")),
                        reps=str(item.get("reps", "")),
                        weight_label="PB Weight",
                        reps_label="PB Reps",
                    )
                )
        return sorted(points, key=lambda point: point.date, reverse=True)

    def _current_pb_records(self, points: list[ExercisePoint]) -> list[ExercisePoint]:
        records: dict[str, ExercisePoint] = {}
        for point in points:
            if point.numeric_weight <= 0:
                continue
            current = records.get(point.exercise)
            if (
                current is None
                or point.numeric_weight > current.numeric_weight
                or (point.numeric_weight == current.numeric_weight and point.date > current.date)
            ):
                records[point.exercise] = point
        return [records[name] for name in sorted(records, key=str.casefold)]

    def _open_settings(self) -> None:
        body = self._open_page("Settings")
        always_on_top = tk.BooleanVar(value=bool(self.store.settings.get("always_on_top", False)))

        def toggle() -> None:
            self.store.set_always_on_top(bool(always_on_top.get()))
            self._apply_always_on_top()

        ttk.Checkbutton(body, text="Always On Top", variable=always_on_top, command=toggle).grid(row=0, column=0, sticky="w")

    def _open_data_window(self) -> None:
        body = self._open_page("Data")
        body.grid_rowconfigure(0, weight=0)
        body.grid_rowconfigure(1, weight=0)
        body.grid_rowconfigure(2, weight=0)
        body.grid_rowconfigure(3, weight=1)

        exercise_points = self._exercise_points()
        pb_points = self._pb_points()
        routine_names = sorted(
            set(self.store.routines) | {log.get("routine", "") for log in self.store.routine_logs if log.get("routine", "")},
            key=str.casefold,
        )
        exercise_names = sorted(
            {point.exercise for point in exercise_points} | {row["exercise"] for routine in self.store.routines.values() for row in routine},
            key=str.casefold,
        )
        selected_item = tk.StringVar(value=routine_names[0] if routine_names else (exercise_names[0] if exercise_names else "Select Data"))
        selected_type = tk.StringVar(value="routine" if routine_names else "exercise")

        picker = tk.Menubutton(
            body,
            textvariable=selected_item,
            background=self.input_bg,
            foreground=self.text,
            activebackground="#253044",
            activeforeground=self.text,
            relief="flat",
            anchor="w",
            padx=10,
            pady=4,
            font=("Segoe UI", 9),
            cursor="hand2",
        )
        picker.grid(row=0, column=0, sticky="ew")
        picker_menu = tk.Menu(
            picker,
            tearoff=False,
            background=self.input_bg,
            foreground=self.text,
            activebackground="#253044",
            activeforeground=self.text,
            disabledforeground=self.muted,
        )
        picker.configure(menu=picker_menu)

        routine_exercises: dict[str, list[str]] = {}
        routine_exercise_names: set[str] = set()
        for routine in routine_names:
            names = {
                str(row.get("exercise", "")).strip()
                for row in self.store.routines.get(routine, [])
                if str(row.get("exercise", "")).strip()
            }
            for log in self.store.routine_logs:
                if log.get("routine", "") != routine:
                    continue
                for item in log.get("exercises", []):
                    exercise = str(item.get("exercise", "")).strip()
                    if exercise:
                        names.add(exercise)
            routine_exercises[routine] = sorted(names, key=str.casefold)
            routine_exercise_names.update(names)
        other_exercises = sorted(set(exercise_names) - routine_exercise_names, key=str.casefold)

        def choose_data(kind: str, value: str) -> None:
            selected_type.set(kind)
            selected_item.set(value)
            refresh_data()

        for routine in routine_names:
            picker_menu.add_command(
                label=routine,
                command=lambda name=routine: choose_data("routine", name),
                font=("Segoe UI", 9, "bold"),
            )
            for exercise in routine_exercises[routine]:
                picker_menu.add_command(label=f"  {exercise}", command=lambda name=exercise: choose_data("exercise", name))
        picker_menu.add_command(label="Other", command=lambda: None, font=("Segoe UI", 9, "bold"))
        for exercise in other_exercises:
            picker_menu.add_command(label=f"  {exercise}", command=lambda name=exercise: choose_data("exercise", name))

        chart = TrendChart(body, height=190)
        chart.grid(row=1, column=0, sticky="ew", pady=(12, 14))

        ttk.Label(body, text="PB HISTORY", style="Head.TLabel").grid(row=2, column=0, sticky="w")
        history_table = ttk.Treeview(
            body,
            columns=("date", "exercise", "weight", "reps"),
            show="headings",
            selectmode="browse",
        )
        for key, label, width in [
            ("date", "Date", 78),
            ("exercise", "Exercise", 168),
            ("weight", "Weight", 68),
            ("reps", "Reps", 52),
        ]:
            history_table.heading(key, text=label, anchor="center")
            history_table.column(key, width=width, anchor="center", stretch=False)
        history_table.grid(row=3, column=0, sticky="nsew", pady=(8, 0))

        def fit_data_layout(_event: tk.Event | None = None) -> None:
            width = max(body.winfo_width(), 1)
            height = max(body.winfo_height(), 1)
            chart_height = max(120, min(220, int(height * 0.34)))
            chart.configure(height=chart_height)

            table_width = max(history_table.winfo_width() - 4, width - 4, 1)
            date_w = 78
            weight_w = 68
            reps_w = 52
            exercise_w = max(96, table_width - date_w - weight_w - reps_w)
            for key, width_value in [
                ("date", date_w),
                ("exercise", exercise_w),
                ("weight", weight_w),
                ("reps", reps_w),
            ]:
                history_table.column(key, width=max(1, int(width_value)), minwidth=1, stretch=False)

            row_height = 30
            reserved = chart_height + picker.winfo_height() + 62
            visible_rows = max(4, int(max(height - reserved, row_height * 4) / row_height))
            history_table.configure(height=visible_rows)

        def routine_summaries(routine: str) -> list[dict]:
            summaries = [
                summarize_routine_log(log)
                for log in self.store.routine_logs
                if log.get("routine", "") == routine
            ]
            return sorted(summaries, key=lambda summary: summary["date"], reverse=True)

        def selected_kind() -> tuple[str, str]:
            selected = selected_item.get()
            kind = selected_type.get()
            if kind in {"routine", "exercise"} and selected:
                return kind, selected
            return "", selected

        def refresh_data() -> None:
            for row_id in history_table.get_children():
                history_table.delete(row_id)

            kind, selected = selected_kind()
            if kind == "routine":
                chart_points = [
                    ExercisePoint(
                        date=summary["date"],
                        routine=summary["routine"],
                        exercise=summary["routine"],
                        weight=format_weight(summary["total_weight"]),
                        reps=f"{summary['total_sets']}, Avg Reps: {format_whole_number(summary['average_reps'])}",
                        weight_label="Total Moved",
                        reps_label="Sets",
                    )
                    for summary in routine_summaries(selected)
                ]
                history_points = [point for point in pb_points if point.routine == selected]
            elif kind == "exercise":
                chart_points = [point for point in exercise_points if point.exercise == selected]
                history_points = [point for point in pb_points if point.exercise == selected]
            else:
                chart_points = []
                history_points = pb_points

            chart.draw(chart_points)
            for point in history_points:
                history_table.insert(
                    "",
                    tk.END,
                    values=(point.date, point.exercise, format_weight(point.weight), point.reps),
                )

        chart.bind("<Configure>", lambda _event: refresh_data())
        body.bind("<Configure>", fit_data_layout)
        history_table.bind("<Configure>", fit_data_layout)
        self.after_idle(fit_data_layout)
        refresh_data()

    def _open_history_window(self) -> None:
        body = self._open_page("History")
        body.grid_rowconfigure(1, weight=1)

        top_actions = ttk.Frame(body, style="Main.TFrame")
        top_actions.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        top_actions.grid_columnconfigure(2, weight=1)

        table = ttk.Treeview(body, columns=("date", "routine", "exercises"), show="headings", selectmode="extended")
        for key, label, width in [
            ("date", "Date", 100),
            ("routine", "Routine", 190),
            ("exercises", "Exercises", 80),
        ]:
            table.heading(key, text=label, anchor="center")
            table.column(key, width=width, anchor="center")
        table.grid(row=1, column=0, sticky="nsew", pady=(0, 12))

        status = tk.StringVar()
        ttk.Label(body, textvariable=status, style="Muted.TLabel").grid(row=2, column=0, sticky="w")

        bottom_actions = ttk.Frame(body, style="Main.TFrame")
        bottom_actions.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        bottom_actions.grid_columnconfigure(0, weight=1)

        empty_label = ttk.Label(body, text="No saved workouts yet.", style="Muted.TLabel")

        def refresh() -> None:
            for row_id in table.get_children():
                table.delete(row_id)
            for index, log in reversed(list(enumerate(self.store.routine_logs))):
                table.insert(
                    "",
                    tk.END,
                    iid=str(index),
                    values=(log.get("date", ""), log.get("routine", ""), len(log.get("exercises", []))),
                )
            if self.store.routine_logs:
                empty_label.grid_remove()
            else:
                empty_label.grid(row=1, column=0, sticky="n", pady=(92, 0))

        def select_all() -> None:
            rows = table.get_children()
            if rows:
                table.selection_set(rows)
                table.focus(rows[0])
                status.set("")

        def deselect_all() -> None:
            table.selection_remove(table.selection())
            status.set("")

        def toggle_row_selection(event: tk.Event) -> str | None:
            region = table.identify_region(event.x, event.y)
            if region not in {"cell", "tree"}:
                return None
            row_id = table.identify_row(event.y)
            if not row_id:
                return "break"
            if row_id in table.selection():
                table.selection_remove(row_id)
            else:
                table.selection_add(row_id)
                table.focus(row_id)
            status.set("")
            return "break"

        def delete_selected() -> None:
            selected = table.selection()
            if not selected:
                status.set("Select saved workouts to delete.")
                return
            indices = [int(item) for item in selected]
            if len(indices) == 1:
                log = self.store.routine_logs[indices[0]]
                message = f"Delete {log.get('routine', 'Workout')} from {log.get('date', '')}?"
            else:
                message = f"Delete {len(indices)} saved workouts from history?"
            if not messagebox.askyesno("Delete history", message, parent=self):
                return
            deleted_count = len(indices)
            self.store.delete_routine_logs(indices)
            status.set("")
            refresh()
            messagebox.showinfo("History deleted", f"Deleted {deleted_count} history entries.", parent=self)

        def export_all() -> None:
            target = filedialog.asksaveasfilename(
                parent=self,
                title="Export History",
                defaultextension=".json",
                initialfile=f"workout_history_{TODAY}.json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if not target:
                return
            try:
                Path(target).write_text(json.dumps(self.store.history_export_payload(), indent=2), encoding="utf-8")
            except OSError as exc:
                status.set(f"Export failed: {exc}")
                return
            status.set("")
            messagebox.showinfo("History exported", f"Exported {len(self.store.routine_logs)} history entries.", parent=self)

        def import_history() -> None:
            source = filedialog.askopenfilename(
                parent=self,
                title="Import History",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if not source:
                return
            try:
                payload = json.loads(Path(source).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                status.set(f"Import failed: {exc}")
                return
            imported, skipped = self.store.import_history_payload(payload)
            refresh()
            status.set("")
            messagebox.showinfo(
                "History imported",
                f"Imported {imported} new history entries. Skipped {skipped} duplicate-date or invalid entries.",
                parent=self,
            )

        table.bind("<Button-1>", toggle_row_selection)
        RoundedButton(top_actions, "Export All", export_all, width=86).grid(row=0, column=0, sticky="w")
        RoundedButton(top_actions, "Import", import_history, width=72).grid(row=0, column=1, sticky="w", padx=(8, 0))
        RoundedButton(top_actions, "Select All", select_all, width=86).grid(row=0, column=3, sticky="e", padx=(0, 8))
        RoundedButton(top_actions, "Deselect All", deselect_all, width=96).grid(row=0, column=4, sticky="e")
        RoundedButton(bottom_actions, "Delete", delete_selected, width=82).grid(row=0, column=1, sticky="e")
        refresh()


class NewRoutineWindow(tk.Toplevel):
    def __init__(self, parent: WorkoutPlannerApp) -> None:
        super().__init__(parent)
        self.title("New Routine")
        self.iconphoto(False, parent.app_icon)
        place_on_parent_screen(parent, self, 320, 150)
        layer_popup(parent, self)
        self.resizable(False, False)
        self.configure(background=parent.bg)
        self.parent = parent
        self.routine_name = tk.StringVar()

        panel = ttk.Frame(self, style="Main.TFrame", padding=18)
        panel.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(panel, text="New Routine", style="Title.TLabel").pack(anchor="w")
        entry = ttk.Entry(panel, textvariable=self.routine_name)
        entry.pack(fill="x", pady=(14, 12))
        entry.focus_set()
        RoundedButton(panel, "Create", self._create, width=86, variant="primary").pack(anchor="e")
        self.bind("<Return>", lambda _event: self._create())

    def _create(self) -> None:
        self.parent.create_routine(self.routine_name.get())
        if self.routine_name.get().strip() in self.parent.store.routines:
            self.destroy()


class SettingsWindow(tk.Toplevel):
    def __init__(self, parent: WorkoutPlannerApp, store: WorkoutStore) -> None:
        super().__init__(parent)
        self.title("Settings")
        self.iconphoto(False, parent.app_icon)
        place_on_parent_screen(parent, self, 300, 140)
        layer_popup(parent, self)
        self.resizable(False, False)
        self.configure(background=parent.bg)
        self.parent = parent
        self.store = store
        self.always_on_top = tk.BooleanVar(value=bool(store.settings.get("always_on_top", False)))

        panel = ttk.Frame(self, style="Main.TFrame", padding=18)
        panel.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(panel, text="Settings", style="Title.TLabel").pack(anchor="w")
        ttk.Checkbutton(panel, text="Always On Top", variable=self.always_on_top, command=self._toggle).pack(
            anchor="w", pady=(18, 0)
        )

    def _toggle(self) -> None:
        enabled = bool(self.always_on_top.get())
        self.store.set_always_on_top(enabled)
        self.parent._apply_always_on_top()


class HistoryWindow(tk.Toplevel):
    def __init__(self, parent: WorkoutPlannerApp, store: WorkoutStore) -> None:
        super().__init__(parent)
        self.title("History")
        self.iconphoto(False, parent.app_icon)
        place_on_parent_screen(parent, self, 440, 430)
        layer_popup(parent, self)
        self.minsize(380, 340)
        self.configure(background=parent.bg)
        self.parent = parent
        self.store = store

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        main = ttk.Frame(self, style="Main.TFrame", padding=18)
        main.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        ttk.Label(main, text="History", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.table = ttk.Treeview(main, columns=("date", "routine", "exercises"), show="headings", selectmode="extended")
        for key, label, width in [
            ("date", "Date", 100),
            ("routine", "Routine", 190),
            ("exercises", "Exercises", 80),
        ]:
            self.table.heading(key, text=label, anchor="center")
            self.table.column(key, width=width, anchor="center")
        self.table.grid(row=1, column=0, sticky="nsew", pady=(14, 12))

        actions = ttk.Frame(main, style="Main.TFrame")
        actions.grid(row=2, column=0, sticky="ew")
        actions.grid_columnconfigure(0, weight=1)
        RoundedButton(actions, "Select All", self._select_all, width=106).grid(row=0, column=1, sticky="e", padx=(0, 8))
        RoundedButton(actions, "Delete", self._delete_selected, width=96).grid(row=0, column=2, sticky="e")

        self.empty_label = ttk.Label(main, text="No saved workouts yet.", style="Muted.TLabel")
        self._refresh()

    def _refresh(self) -> None:
        for row in self.table.get_children():
            self.table.delete(row)
        for index, log in reversed(list(enumerate(self.store.routine_logs))):
            exercise_count = len(log.get("exercises", []))
            self.table.insert(
                "",
                tk.END,
                iid=str(index),
                values=(log.get("date", ""), log.get("routine", ""), exercise_count),
            )
        if self.store.routine_logs:
            self.empty_label.grid_remove()
        else:
            self.empty_label.grid(row=1, column=0, sticky="n", pady=(92, 0))

    def _delete_selected(self) -> None:
        selected = self.table.selection()
        if not selected:
            messagebox.showinfo("Select history", "Select saved workouts to delete.", parent=self)
            return
        indices = [int(item) for item in selected]
        if len(indices) == 1:
            log = self.store.routine_logs[indices[0]]
            message = f"Delete {log.get('routine', 'Workout')} from {log.get('date', '')}?"
        else:
            message = f"Delete {len(indices)} saved workouts from history?"
        if not messagebox.askyesno("Delete history", message, parent=self):
            return
        self.store.delete_routine_logs(indices)
        self._refresh()

    def _select_all(self) -> None:
        rows = self.table.get_children()
        if rows:
            self.table.selection_set(rows)
            self.table.focus(rows[0])


class DataWindow(tk.Toplevel):
    def __init__(self, parent: WorkoutPlannerApp, store: WorkoutStore) -> None:
        super().__init__(parent)
        self.title("Data")
        self.iconphoto(False, parent.app_icon)
        place_on_parent_screen(parent, self, 800, 540)
        layer_popup(parent, self)
        self.minsize(720, 480)
        self.configure(background=parent.bg)

        self.store = store
        points = self._exercise_points()
        exercises = sorted({point.exercise for point in points} | {row["exercise"] for routine in store.routines.values() for row in routine})
        self.selected_exercise = tk.StringVar(value=exercises[0] if exercises else "Exercise")
        self.points = points
        self._build(exercises)
        self._refresh()

    def _exercise_points(self) -> list[ExercisePoint]:
        points = []
        for log in self.store.routine_logs:
            for item in log.get("exercises", []):
                points.append(
                    ExercisePoint(
                        date=log.get("date", ""),
                        routine=log.get("routine", ""),
                        exercise=item.get("exercise", ""),
                        weight=str(item.get("weight", "")),
                        reps=str(item.get("reps", "")),
                    )
                )
        return sorted(points, key=lambda point: point.date, reverse=True)

    def _build(self, exercises: list[str]) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        main = ttk.Frame(self, style="Main.TFrame", padding=18)
        main.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)

        header = ttk.Frame(main, style="Main.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        ttk.Label(header, text="Data", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        picker = ttk.Combobox(header, textvariable=self.selected_exercise, values=exercises, state="readonly", width=26)
        picker.grid(row=0, column=1, sticky="e")
        picker.bind("<<ComboboxSelected>>", lambda _event: self._refresh_chart())

        self.chart = TrendChart(main, height=220)
        self.chart.grid(row=1, column=0, sticky="ew", pady=(14, 14))
        self.chart.bind("<Configure>", lambda _event: self._refresh_chart())

        self.table = ttk.Treeview(main, columns=("date", "routine", "exercise", "weight", "reps"), show="headings")
        for key, label, width in [
            ("date", "Date", 95),
            ("routine", "Routine", 140),
            ("exercise", "Exercise", 210),
            ("weight", "Weight", 90),
            ("reps", "Reps", 100),
        ]:
            self.table.heading(key, text=label, anchor="center")
            self.table.column(key, width=width, anchor="center")
        self.table.grid(row=2, column=0, sticky="nsew")

    def _refresh(self) -> None:
        for row in self.table.get_children():
            self.table.delete(row)
        for point in self.points:
            self.table.insert("", tk.END, values=(point.date, point.routine, point.exercise, point.weight, point.reps))
        self._refresh_chart()

    def _refresh_chart(self) -> None:
        if not hasattr(self, "chart"):
            return
        exercise = self.selected_exercise.get()
        self.chart.draw([point for point in self.points if point.exercise == exercise])


if __name__ == "__main__":
    app = WorkoutPlannerApp()
    app.mainloop()
