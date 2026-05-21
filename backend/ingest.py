"""Read the 15-sheet master workbook and validate Order_Data per spec §5/§6.

Every sheet uses ROW 1 = banner, ROW 2 = column names, ROW 3+ = data. The literal
"skiprows=2" wording from earlier internal docs is wrong (it would skip both the
banner and the headers); we use ``header=1`` everywhere. Test S6 plus the live
upload validator together enforce this.

The V4 ingest is strict: any missing column or null cell in Order_Data causes the
upload to be REJECTED (spec §6, §16 rule #6). No silent derivation. The frontend
surfaces the error directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


# Per spec §6, Order_Data must have these 20 columns in this order, all populated.
ORDER_DATA_REQUIRED_COLS: list[str] = [
    "Order_ID",
    "Origin_Node",
    "Destination_Node",
    "Destination_Node_Pincode",
    "Weight_kg",
    "Volume_m3",
    "Order_Placed_Time",
    "Customer_SLA_Deadline",
    "Priority",
    "PickPack_Time_min",
    "Order_Ready_Time",
    "FC_Region",
    "DS_City",
    "SLA_hrs",
    "SLA_Tier",
    "WISMO_Cost_INR",
    "Compensation_INR",
    "Repurchase_Risk_INR",
    "Total_Penalty_INR",
    "Ops_SLA_Deadline",
]

# Spec §5 — the 15 sheets in order.
REQUIRED_SHEETS_IN_ORDER: list[str] = [
    "Project_Overview",
    "Origin_Master",
    "Intermediate_Master",
    "Destination_Master",
    "Vehicle_Types",
    "Carrier_Master",
    "SLA_Config",
    "Penalty_Config",
    "Pick_Pack_Config",
    "Origin_Order_Waves",
    "Origin_Dispatch_Waves",
    "Node_Schedule",
    "DS_Dispatch_Waves",
    "Lane_Distance_Matrix",
    "Order_Data",
]

DATA_SHEETS: list[str] = [s for s in REQUIRED_SHEETS_IN_ORDER if s != "Project_Overview"]


@dataclass
class IngestError:
    sheet: str | None
    column: str | None
    message: str

    def to_dict(self) -> dict:
        return {"sheet": self.sheet, "column": self.column, "message": self.message}


@dataclass
class IngestResult:
    """Container for the parsed master workbook.

    ``ok=False`` means at least one validation error was found; callers (the
    /api/upload endpoint) MUST reject the upload in that case and surface the
    errors list to the UI — V4 §6 forbids silent recovery.
    """
    ok: bool
    errors: list[IngestError] = field(default_factory=list)
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    preview_stats: dict = field(default_factory=dict)


def read_master_workbook(path: str | Path) -> IngestResult:
    """Read the master Excel and validate per spec §5 / §6.

    Returns ``IngestResult`` regardless of success; check ``.ok`` and ``.errors``
    before using ``.frames``.
    """
    path = Path(path)
    result = IngestResult(ok=True)

    if not path.exists():
        result.ok = False
        result.errors.append(IngestError(None, None, f"File not found: {path}"))
        return result

    # --- Sheet presence + order check (§5) ---
    try:
        xls = pd.ExcelFile(path, engine="openpyxl")
    except Exception as e:
        result.ok = False
        result.errors.append(IngestError(None, None, f"Could not open workbook: {e}"))
        return result

    actual_sheets = list(xls.sheet_names)
    if actual_sheets != REQUIRED_SHEETS_IN_ORDER:
        # Find missing / extra / out-of-order
        missing = [s for s in REQUIRED_SHEETS_IN_ORDER if s not in actual_sheets]
        extra = [s for s in actual_sheets if s not in REQUIRED_SHEETS_IN_ORDER]
        if missing:
            result.ok = False
            result.errors.append(IngestError(
                None, None,
                f"Workbook is missing required sheet(s): {missing}. "
                "The master Excel must contain all 15 sheets per spec §5."
            ))
        if extra:
            result.errors.append(IngestError(
                None, None, f"Workbook has unexpected sheet(s): {extra} (ignored)."
            ))
        # Order mismatch is a warning if all required are present
        if not missing:
            result.errors.append(IngestError(
                None, None,
                f"Sheet order differs from spec §5. Found: {actual_sheets}. "
                "Order is informational; processing continues by name."
            ))

    # --- Per-sheet load with header=1 ---
    # Even if some sheets failed presence check, load the ones we can so
    # downstream code can show a partial preview.
    for sheet in DATA_SHEETS:
        if sheet not in actual_sheets:
            continue
        try:
            df = pd.read_excel(path, sheet_name=sheet, header=1, engine="openpyxl")
            result.frames[sheet] = df
        except Exception as e:
            result.ok = False
            result.errors.append(IngestError(sheet, None, f"Could not parse sheet: {e}"))

    # --- Strict Order_Data validation (§6) ---
    if "Order_Data" in result.frames:
        od = result.frames["Order_Data"]
        # Column count
        if len(od.columns) != 20:
            result.ok = False
            result.errors.append(IngestError(
                "Order_Data", None,
                f"Order_Data sheet has {len(od.columns)} columns; 20 required. "
                "See spec §6 for the column list."
            ))
        # Column names (in order)
        for i, want in enumerate(ORDER_DATA_REQUIRED_COLS):
            if i >= len(od.columns):
                break
            actual = str(od.columns[i])
            if actual != want:
                result.ok = False
                result.errors.append(IngestError(
                    "Order_Data", actual,
                    f"Column {i+1} should be '{want}' but is '{actual}'."
                ))
        # Null check on every cell — V4 forbids silent derivation
        if len(od) > 0:
            null_counts = od.isnull().sum()
            for col, n in null_counts.items():
                if n > 0:
                    result.ok = False
                    result.errors.append(IngestError(
                        "Order_Data", str(col),
                        f"Column '{col}' has {int(n)} null cell(s). "
                        "V4 §6 requires every cell populated; the app does NOT derive missing values."
                    ))

    # --- Preview stats for the UI ---
    if "Order_Data" in result.frames:
        od = result.frames["Order_Data"]
        result.preview_stats["orders"] = len(od)
    if "Origin_Master" in result.frames:
        result.preview_stats["fcs"] = len(result.frames["Origin_Master"])
    if "Intermediate_Master" in result.frames:
        result.preview_stats["scs"] = len(result.frames["Intermediate_Master"])
    if "Destination_Master" in result.frames:
        dm = result.frames["Destination_Master"]
        result.preview_stats["dses"] = len(dm)
        if "DS_Type" in dm.columns:
            result.preview_stats["dses_active"] = int((dm["DS_Type"] == "Active").sum())
            result.preview_stats["dses_minor"] = int((dm["DS_Type"] != "Active").sum())
    if "Carrier_Master" in result.frames:
        cm = result.frames["Carrier_Master"]
        if "Carrier_ID" in cm.columns:
            result.preview_stats["carriers"] = int(cm["Carrier_ID"].nunique())
    if "Vehicle_Types" in result.frames:
        result.preview_stats["vehicles"] = len(result.frames["Vehicle_Types"])
    if "Lane_Distance_Matrix" in result.frames:
        ld = result.frames["Lane_Distance_Matrix"]
        if "Lane_Type" in ld.columns:
            counts = ld["Lane_Type"].value_counts().to_dict()
            result.preview_stats["lanes_by_type"] = {str(k): int(v) for k, v in counts.items()}
            result.preview_stats["lanes_total"] = len(ld)

    # Active wave
    for wave_sheet, key in [
        ("Origin_Order_Waves", "active_order_wave"),
        ("Origin_Dispatch_Waves", "active_dispatch_wave"),
    ]:
        if wave_sheet in result.frames:
            df = result.frames[wave_sheet]
            if "Active_Wave" in df.columns and "Wave_ID" in df.columns:
                active = df[df["Active_Wave"] == 1]
                if len(active) >= 1:
                    result.preview_stats[key] = str(active["Wave_ID"].iloc[0])

    return result


def summarise(frames: dict[str, pd.DataFrame]) -> dict:
    """Convenience: a smaller numeric summary used by the /api/master_summary endpoint."""
    out: dict = {}
    if "Origin_Master" in frames:
        out["fcs"] = len(frames["Origin_Master"])
    if "Intermediate_Master" in frames:
        out["scs"] = len(frames["Intermediate_Master"])
    if "Destination_Master" in frames:
        dm = frames["Destination_Master"]
        out["dses_active"] = int((dm.get("DS_Type", pd.Series(dtype=str)) == "Active").sum())
        out["dses_minor"] = int((dm.get("DS_Type", pd.Series(dtype=str)) != "Active").sum())
    if "Lane_Distance_Matrix" in frames:
        ld = frames["Lane_Distance_Matrix"]
        c = ld["Lane_Type"].value_counts()
        out["lanes_fc_sc"] = int(c.get("FC_SC", 0))
        out["lanes_sc_ds"] = int(c.get("SC_DS", 0))
        out["lanes_fc_ds_direct"] = int(c.get("FC_DS", 0))
        out["lanes_sc_sc"] = int(c.get("SC_SC", 0))
    if "Carrier_Master" in frames:
        out["carriers"] = int(frames["Carrier_Master"]["Carrier_ID"].nunique())
    if "Vehicle_Types" in frames:
        out["vehicles"] = len(frames["Vehicle_Types"])
    if "Order_Data" in frames:
        out["orders"] = len(frames["Order_Data"])
    for w, k in [("Origin_Order_Waves", "active_order_wave"),
                 ("Origin_Dispatch_Waves", "active_dispatch_wave")]:
        if w in frames:
            df = frames[w]
            if "Active_Wave" in df.columns:
                active = df[df["Active_Wave"] == 1]
                if len(active):
                    out[k] = str(active["Wave_ID"].iloc[0])
    return out
