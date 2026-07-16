import csv
import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

from .models import CaseRecord, SeedRecord, TransactionRecord, VersionRecord


class Repository(ABC):
    @abstractmethod
    def create_case(self, case: CaseRecord) -> CaseRecord: ...
    @abstractmethod
    def list_cases(self) -> list[CaseRecord]: ...
    @abstractmethod
    def get_case(self, case_id: str) -> CaseRecord: ...


class FileRepository(Repository):
    SUBDIRS = ("materials", "extracted", "drafts", "versions", "analysis", "exports", "audit")

    def __init__(self, data_dir: Path):
        self.root = Path(data_dir)
        self.cases_dir = self.root / "cases"
        self.cases_dir.mkdir(parents=True, exist_ok=True)

    def case_dir(self, case_id: str) -> Path:
        path = self.cases_dir / case_id
        if not path.exists():
            raise KeyError(case_id)
        return path

    def create_case(self, case: CaseRecord) -> CaseRecord:
        path = self.cases_dir / case.case_id
        path.mkdir(parents=True, exist_ok=False)
        for name in self.SUBDIRS:
            (path / name).mkdir()
        self._write_json(path / "case.json", case.model_dump(mode="json"))
        return case

    def list_cases(self) -> list[CaseRecord]:
        records = [CaseRecord.model_validate_json(path.read_text("utf-8")) for path in self.cases_dir.glob("*/case.json")]
        return sorted(records, key=lambda item: item.updated_at, reverse=True)

    def get_case(self, case_id: str) -> CaseRecord:
        return CaseRecord.model_validate_json((self.case_dir(case_id) / "case.json").read_text("utf-8"))

    def save_case(self, case: CaseRecord) -> CaseRecord:
        case.updated_at = datetime.now(timezone.utc)
        self._write_json(self.case_dir(case.case_id) / "case.json", case.model_dump(mode="json"))
        return case

    def append_audit(self, case_id: str, event: dict) -> None:
        event = {"timestamp": datetime.now(timezone.utc).isoformat(), **event}
        with (self.case_dir(case_id) / "audit" / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def list_drafts(self, case_id: str) -> list[TransactionRecord]:
        path = self.case_dir(case_id) / "drafts" / "transactions.jsonl"
        if not path.exists():
            return []
        return [TransactionRecord.model_validate_json(line) for line in path.read_text("utf-8").splitlines() if line]

    def save_drafts(self, case_id: str, records: list[TransactionRecord]) -> None:
        path = self.case_dir(case_id) / "drafts" / "transactions.jsonl"
        path.write_text("\n".join(record.model_dump_json() for record in records) + ("\n" if records else ""), "utf-8")

    def add_draft(self, case_id: str, record: TransactionRecord) -> TransactionRecord:
        records = self.list_drafts(case_id)
        records.append(record)
        self.save_drafts(case_id, records)
        self.append_audit(case_id, {"event":"draft_created","transaction_id":record.transaction_id})
        return record

    def update_draft(self, case_id: str, transaction_id: str, updates: dict) -> TransactionRecord:
        records = self.list_drafts(case_id)
        for index, record in enumerate(records):
            if record.transaction_id == transaction_id:
                records[index] = record.model_copy(update={k:v for k,v in updates.items() if v is not None})
                if records[index].review_status == "confirmed":
                    records[index].provenance = "human_confirmed"
                self.save_drafts(case_id, records)
                self.append_audit(case_id, {"event":"draft_updated","transaction_id":transaction_id,"fields":list(updates)})
                return records[index]
        raise KeyError(transaction_id)

    def create_version(self, case_id: str, name: str) -> VersionRecord:
        records = self.list_drafts(case_id)
        if not records or any(record.review_status != "confirmed" for record in records):
            raise ValueError("all draft transactions must be confirmed")
        versions = self.list_versions(case_id)
        version_id = f"V{len(versions)+1:03d}"
        path = self.case_dir(case_id) / "versions" / f"{version_id}.csv"
        fields = list(TransactionRecord.model_fields)
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for record in records:
                row = record.model_dump(mode="json")
                row["source"] = json.dumps(row["source"], ensure_ascii=False)
                row["confidence"] = json.dumps(row["confidence"], ensure_ascii=False)
                writer.writerow(row)
        version = VersionRecord(version_id=version_id, name=name, created_at=datetime.now(timezone.utc), record_count=len(records), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), csv_path=str(path.relative_to(self.case_dir(case_id))))
        self._write_json(self.case_dir(case_id)/"versions"/f"{version_id}.json", version.model_dump(mode="json"))
        self.append_audit(case_id, {"event":"version_created","version_id":version_id,"sha256":version.sha256})
        return version

    def list_versions(self, case_id: str) -> list[VersionRecord]:
        return [VersionRecord.model_validate_json(path.read_text("utf-8")) for path in sorted((self.case_dir(case_id)/"versions").glob("V*.json"))]

    def save_seed(self, case_id: str, seed: SeedRecord) -> SeedRecord:
        path = self.case_dir(case_id)/"analysis"/"seeds.jsonl"
        with path.open("a",encoding="utf-8") as handle:
            handle.write(seed.model_dump_json()+"\n")
        self.append_audit(case_id,{"event":"seed_confirmed","seed_id":seed.seed_id,"transaction_id":seed.transaction_id})
        return seed

    def list_seeds(self, case_id: str) -> list[SeedRecord]:
        path=self.case_dir(case_id)/"analysis"/"seeds.jsonl"
        return [] if not path.exists() else [SeedRecord.model_validate_json(line) for line in path.read_text("utf-8").splitlines() if line]

    @staticmethod
    def _write_json(path: Path, value: dict) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),"utf-8")
        temp.replace(path)

