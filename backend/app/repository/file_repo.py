import csv
import hashlib
import json
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from ..ingestion.dedup import canonical_records, group_duplicate_records
from ..models import CaseRecord, SeedRecord, TransactionRecord, VersionRecord


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
        self._case_locks: defaultdict[str, RLock] = defaultdict(RLock)

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
        records = [
            CaseRecord.model_validate_json(path.read_text("utf-8"))
            for path in self.cases_dir.glob("*/case.json")
        ]
        return sorted(records, key=lambda item: item.updated_at, reverse=True)

    def get_case(self, case_id: str) -> CaseRecord:
        return CaseRecord.model_validate_json(
            (self.case_dir(case_id) / "case.json").read_text("utf-8")
        )

    def save_case(self, case: CaseRecord) -> CaseRecord:
        case.updated_at = datetime.now(timezone.utc)
        self._write_json(
            self.case_dir(case.case_id) / "case.json", case.model_dump(mode="json")
        )
        return case

    def append_audit(self, case_id: str, event: dict) -> None:
        event = {"timestamp": datetime.now(timezone.utc).isoformat(), **event}
        with (
            self.case_dir(case_id) / "audit" / "events.jsonl"
        ).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def list_drafts(self, case_id: str) -> list[TransactionRecord]:
        path = self.case_dir(case_id) / "drafts" / "transactions.jsonl"
        if not path.exists():
            return []
        return [
            TransactionRecord.model_validate_json(line)
            for line in path.read_text("utf-8").splitlines()
            if line
        ]

    def save_drafts(
        self, case_id: str, records: list[TransactionRecord]
    ) -> None:
        path = self.case_dir(case_id) / "drafts" / "transactions.jsonl"
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(
            "\n".join(record.model_dump_json() for record in records)
            + ("\n" if records else ""),
            "utf-8",
        )
        temp.replace(path)

    def add_draft(
        self, case_id: str, record: TransactionRecord
    ) -> TransactionRecord:
        return self.add_drafts(case_id, [record])[0]

    def add_drafts(
        self, case_id: str, new_records: list[TransactionRecord]
    ) -> list[TransactionRecord]:
        with self._case_locks[case_id]:
            records = group_duplicate_records(
                self.list_drafts(case_id) + new_records
            )
            self.save_drafts(case_id, records)
            created_ids = {record.transaction_id for record in new_records}
            created = [
                record for record in records if record.transaction_id in created_ids
            ]
            self.append_audit(
                case_id, {"event": "drafts_created", "count": len(created)}
            )
            return created

    def replace_drafts_for_source(
        self,
        case_id: str,
        source_file_id: str,
        new_records: list[TransactionRecord],
    ) -> list[TransactionRecord]:
        return self.reconcile_drafts_for_source(
            case_id, source_file_id, new_records, replace_missing=True
        )

    @staticmethod
    def _source_identity(record: TransactionRecord) -> str:
        source = record.source.model_dump(mode="json")
        coordinates = json.dumps(source, ensure_ascii=False, sort_keys=True)
        serial = "".join(
            character for character in record.serial_number.upper() if character.isalnum()
        )
        identity = serial or "|".join(
            (
                record.transaction_time.replace(microsecond=0).isoformat(),
                record.payer_account,
                record.payee_account,
                f"{record.amount:.2f}",
            )
        )
        return f"{coordinates}|{identity}"

    def reconcile_drafts_for_source(
        self,
        case_id: str,
        source_file_id: str,
        new_records: list[TransactionRecord],
        replace_missing: bool,
    ) -> list[TransactionRecord]:
        with self._case_locks[case_id]:
            current = self.list_drafts(case_id)
            retained = [
                record
                for record in current
                if record.source.source_file_id != source_file_id
            ]
            previous = [
                record
                for record in current
                if record.source.source_file_id == source_file_id
            ]
            previous_by_identity: dict[str, list[TransactionRecord]] = defaultdict(list)
            for record in previous:
                previous_by_identity[self._source_identity(record)].append(record)
            reconciled = []
            matched_ids = set()
            for record in new_records:
                candidates = previous_by_identity.get(
                    self._source_identity(record), []
                )
                existing = candidates.pop(0) if candidates else None
                if existing is None:
                    reconciled.append(record)
                    continue
                matched_ids.add(existing.transaction_id)
                if existing.review_status in {"confirmed", "conflict"} or existing.provenance == "human_confirmed":
                    reconciled.append(existing)
                else:
                    reconciled.append(
                        record.model_copy(
                            update={
                                "transaction_id": existing.transaction_id,
                                "review_status": existing.review_status,
                                "review_note": existing.review_note,
                            }
                        )
                    )
            if not replace_missing:
                reconciled.extend(
                    record
                    for record in previous
                    if record.transaction_id not in matched_ids
                )
            records = group_duplicate_records(retained + reconciled)
            self.save_drafts(case_id, records)
            current_ids = {
                record.transaction_id for record in reconciled[: len(new_records)]
            }
            created = [
                record for record in records if record.transaction_id in current_ids
            ]
            self.append_audit(
                case_id,
                {
                    "event": "source_drafts_reconciled",
                    "source_file_id": source_file_id,
                    "count": len(created),
                    "replace_missing": replace_missing,
                },
            )
            return created

    def update_draft(
        self, case_id: str, transaction_id: str, updates: dict
    ) -> TransactionRecord:
        with self._case_locks[case_id]:
            records = self.list_drafts(case_id)
            for index, record in enumerate(records):
                if record.transaction_id == transaction_id:
                    records[index] = record.model_copy(
                        update={k: v for k, v in updates.items() if v is not None}
                    )
                    if records[index].review_status == "confirmed":
                        records[index].provenance = "human_confirmed"
                    records = group_duplicate_records(records)
                    self.save_drafts(case_id, records)
                    self.append_audit(
                        case_id,
                        {
                            "event": "draft_updated",
                            "transaction_id": transaction_id,
                            "fields": list(updates),
                        },
                    )
                    return records[index]
        raise KeyError(transaction_id)

    def create_version(self, case_id: str, name: str) -> VersionRecord:
        records = canonical_records(self.list_drafts(case_id))
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
                row["evidence_locations"] = json.dumps(row["evidence_locations"], ensure_ascii=False)
                row["confidence"] = json.dumps(row["confidence"], ensure_ascii=False)
                writer.writerow(row)
        version = VersionRecord(
            version_id=version_id,
            name=name,
            created_at=datetime.now(timezone.utc),
            record_count=len(records),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            csv_path=str(path.relative_to(self.case_dir(case_id))),
        )
        self._write_json(
            self.case_dir(case_id) / "versions" / f"{version_id}.json",
            version.model_dump(mode="json"),
        )
        self.append_audit(
            case_id,
            {"event": "version_created", "version_id": version_id, "sha256": version.sha256},
        )
        return version

    def list_versions(self, case_id: str) -> list[VersionRecord]:
        return [
            VersionRecord.model_validate_json(path.read_text("utf-8"))
            for path in sorted((self.case_dir(case_id) / "versions").glob("V*.json"))
        ]

    def save_seed(self, case_id: str, seed: SeedRecord) -> SeedRecord:
        path = self.case_dir(case_id) / "analysis" / "seeds.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(seed.model_dump_json() + "\n")
        self.append_audit(
            case_id,
            {
                "event": "seed_confirmed",
                "seed_id": seed.seed_id,
                "transaction_id": seed.transaction_id,
            },
        )
        return seed

    def list_seeds(self, case_id: str) -> list[SeedRecord]:
        path = self.case_dir(case_id) / "analysis" / "seeds.jsonl"
        return (
            []
            if not path.exists()
            else [
                SeedRecord.model_validate_json(line)
                for line in path.read_text("utf-8").splitlines()
                if line
            ]
        )

    def delete_seed(self, case_id: str, seed_id: str) -> bool:
        path = self.case_dir(case_id) / "analysis" / "seeds.jsonl"
        if not path.exists():
            return False
        seeds = [
            SeedRecord.model_validate_json(line)
            for line in path.read_text("utf-8").splitlines()
            if line
        ]
        remaining = [seed for seed in seeds if seed.seed_id != seed_id]
        if len(remaining) == len(seeds):
            return False
        path.write_text(
            "".join(seed.model_dump_json() + "\n" for seed in remaining),
            encoding="utf-8",
        )
        self.append_audit(
            case_id,
            {"event": "seed_cancelled", "seed_id": seed_id},
        )
        return True

    @staticmethod
    def _write_json(path: Path, value: dict) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(
            json.dumps(value, ensure_ascii=False, indent=2), "utf-8"
        )
        temp.replace(path)
