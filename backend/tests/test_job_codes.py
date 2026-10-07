import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database as db


def test_prefix_uses_title_initials():
    assert db.job_code_prefix("Senior AI Engineer") == "SAE"
    assert db.job_code_prefix("Head of Data & Analytics") == "HDA"
    assert db.job_code_prefix("Developer") == "DEV"
    assert db.job_code_prefix("Senior Full Stack Java Developer") == "SFSJ"
    assert db.job_code_prefix("") == "JD"
    assert db.job_code_prefix("C++ / .NET Lead") == "CNL"


class Counters:
    def __init__(self):
        self.seq = {}

    def find_one_and_update(self, query, update, **kwargs):
        self.seq[query["_id"]] = self.seq.get(query["_id"], 0) + 1
        return {"seq": self.seq[query["_id"]]}


class Cursor(list):
    def sort(self, *args, **kwargs):
        return self


class Jds:
    def __init__(self, docs):
        self.docs = docs

    def find_one(self, query, projection=None):
        return next((d for d in self.docs if d.get("job_code") == query["job_code"]), None)

    def find(self, query, projection=None):
        return Cursor(d for d in self.docs if not d.get("job_code"))

    def update_one(self, query, update):
        for d in self.docs:
            if d["id"] == query["id"]:
                d.update(update["$set"])


class FakeDb:
    def __init__(self, docs):
        self.counters = Counters()
        self.job_descriptions = Jds(docs)


def test_codes_are_sequential_per_prefix_and_skip_taken_ones(monkeypatch):
    fake = FakeDb([{"id": 9, "title": "manual", "job_code": "SAE-0002"}])
    monkeypatch.setattr(db, "_database", lambda: fake)
    assert db.generate_job_code("Senior AI Engineer") == "SAE-0001"
    assert db.generate_job_code("Senior AI Engineer") == "SAE-0003"   # 0002 already used
    assert db.generate_job_code("Data Engineer") == "DE-0001"


def test_backfill_gives_old_jds_a_code_once(monkeypatch):
    docs = [{"id": 1, "title": "QA Lead", "job_code": ""}, {"id": 2, "title": "QA Lead"}, {"id": 3, "title": "X", "job_code": "KEEP-1"}]
    fake = FakeDb(docs)
    monkeypatch.setattr(db, "_database", lambda: fake)
    monkeypatch.setattr(db, "_job_codes_backfilled", False)
    assert db.backfill_missing_job_codes() == 2
    assert [d["job_code"] for d in docs] == ["QL-0001", "QL-0002", "KEEP-1"]
    assert db.backfill_missing_job_codes() == 0


from app.job_code_extraction import extract_job_code, find_labelled_job_code


def test_labelled_job_ids_are_found_in_jd_text():
    assert find_labelled_job_code("Job ID: REQ-1023\nRole: Engineer") == "REQ-1023"
    assert find_labelled_job_code("Requisition # 45678") == "45678"
    assert find_labelled_job_code("Job Code - JR_2024/015.") == "JR_2024/015"
    assert find_labelled_job_code("POSITION ID:SAE-0042") == "SAE-0042"
    assert find_labelled_job_code("Req. No. 7781 | Location: Pune") == "7781"


def test_placeholders_and_plain_words_are_ignored():
    assert find_labelled_job_code("Job ID: N/A") == ""
    assert find_labelled_job_code("Job Code: TBD") == ""
    assert find_labelled_job_code("Senior AI Engineer\nWe need 5+ years of Python") == ""
    assert find_labelled_job_code("The job requires travel") == ""
    assert find_labelled_job_code("Requisition: 2 positions, Vacancy: 3") == ""


def test_llm_job_id_is_used_only_when_present_in_document():
    text = "Senior AI Engineer\nReference ABC-778 applies to this opening"
    assert extract_job_code(text, text, "ABC-778") == "ABC-778"
    assert extract_job_code(text, text, "XYZ-999") == ""


class _Inserted:
    inserted_id = 1


def test_document_id_beats_generated_code(monkeypatch):
    import services.jd_service as svc

    captured = {}
    monkeypatch.setattr(svc, "extract_text", lambda path: "Job ID: DOC-5512\nSenior AI Engineer")
    monkeypatch.setattr(svc, "clean_jd_text", lambda text: text)
    monkeypatch.setattr(svc, "extract_jd_json", lambda text: {"job_title": "Senior AI Engineer"})
    monkeypatch.setattr(svc.db, "create_jd", lambda data: captured.update(data) or 7)
    monkeypatch.setattr(svc.db, "get_jd_by_id", lambda *a, **k: {"id": 7})
    monkeypatch.setattr(svc, "_apply_jd_category", lambda jd: jd)

    svc.create_jd_from_path("jd.pdf", "jd.pdf")
    assert captured["job_code"] == "DOC-5512"

    monkeypatch.setattr(svc, "extract_text", lambda path: "Senior AI Engineer\nNo reference given")
    svc.create_jd_from_path("jd.pdf", "jd.pdf")
    assert captured["job_code"] == ""  # empty -> create_jd generates SAE-000N
