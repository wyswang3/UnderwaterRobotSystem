# src/offnav/io/dataset.py
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import glob
import yaml

from offnav.core.types import ImuRawData, DvlRawData, RunMeta, RawRunData
from offnav.io.imu_csv import load_imu_csv
from offnav.io.dvl_csv import load_dvl_csv


@dataclass
class RunSpec:
    run_id: str
    date: Optional[str]
    path: Path
    imu_glob: str
    dvl_glob: str
    note: Optional[str] = None


class DatasetIndex:
    def __init__(self, cfg_path: Path):
        self.cfg_path = cfg_path
        self.data_root: Path = Path(".")
        self.runs: Dict[str, RunSpec] = {}
        self._load_yaml()

    def _load_yaml(self) -> None:
        with self.cfg_path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        self.data_root = Path(cfg.get("data_root", "./data")).resolve()
        runs_cfg = cfg.get("runs", [])

        runs: Dict[str, RunSpec] = {}
        for item in runs_cfg:
            run_id = item["id"]
            date = item.get("date")
            sub_path = Path(item["path"])
            imu_glob = item["imu_glob"]
            dvl_glob = item["dvl_glob"]
            note = item.get("note")

            runs[run_id] = RunSpec(
                run_id=run_id,
                date=date,
                path=sub_path,
                imu_glob=imu_glob,
                dvl_glob=dvl_glob,
                note=note,
            )

        self.runs = runs

    # ---- 公共 API ----

    def list_runs(self) -> List[RunSpec]:
        return list(self.runs.values())

    def get_run_spec(self, run_id: str) -> RunSpec:
        if run_id not in self.runs:
            raise KeyError(f"Unknown run_id={run_id!r}, available={list(self.runs.keys())}")
        return self.runs[run_id]

    def load_run(self, run_id: str) -> RawRunData:
        spec = self.get_run_spec(run_id)
        run_dir = self.data_root / spec.path

        if not run_dir.exists():
            raise FileNotFoundError(f"Run directory not found: {run_dir}")

        # IMU
        imu_paths = sorted(glob.glob(str(run_dir / spec.imu_glob)))
        if not imu_paths:
            raise FileNotFoundError(f"No IMU CSV for run={run_id} with glob={spec.imu_glob}")
        if len(imu_paths) > 1:
            import pandas as pd
            imu_dfs = [load_imu_csv(p).df for p in imu_paths]
            imu_df = pd.concat(imu_dfs, ignore_index=True)
            imu_raw = ImuRawData(df=imu_df, source_path=Path(imu_paths[0]))
        else:
            imu_raw = load_imu_csv(imu_paths[0])

        # DVL
        dvl_paths = sorted(glob.glob(str(run_dir / spec.dvl_glob)))
        if not dvl_paths:
            raise FileNotFoundError(f"No DVL CSV for run={run_id} with glob={spec.dvl_glob}")
        if len(dvl_paths) > 1:
            import pandas as pd
            dvl_dfs = [load_dvl_csv(p).df for p in dvl_paths]
            dvl_df = pd.concat(dvl_dfs, ignore_index=True)
            dvl_raw = DvlRawData(df=dvl_df, source_path=Path(dvl_paths[0]))
        else:
            dvl_raw = load_dvl_csv(dvl_paths[0])

        # meta.yaml（可选）
        meta_path = run_dir / "meta.yaml"
        date = spec.date
        note = spec.note
        extra = {}
        if meta_path.exists():
            with meta_path.open("r", encoding="utf-8") as f:
                extra = yaml.safe_load(f) or {}
                date = extra.get("date", date)
                note = extra.get("note", note)

        meta = RunMeta(run_id=run_id, date=date, note=note, extra=extra)
        return RawRunData(run_id=run_id, imu=imu_raw, dvl=dvl_raw, meta=meta)
