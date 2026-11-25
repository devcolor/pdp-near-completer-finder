"""Upload checks: a missing column is rejected and nothing is saved."""

from app.institution_dashboard import data
from app.institution_dashboard.uploads import DATASETS, column_problems, required_columns


def test_missing_column_is_named() -> None:
    """A file without a current column says which column is missing."""
    problem = column_problems("students.csv", b"Student GUID\n", ["Student GUID", "Cohort"])
    assert problem == "students.csv is missing Cohort."


def test_extra_column_is_allowed() -> None:
    """A file may add columns. It still has to keep the current ones."""
    content = b"Student GUID,Cohort,Extra\n"
    assert column_problems("students.csv", content, ["Student GUID", "Cohort"]) is None


def test_upload_rejects_a_missing_column_and_keeps_the_files(client, monkeypatch, tmp_path) -> None:
    """One bad file fails the whole set, and the dashboard files stay where they were."""
    monkeypatch.setattr(data, "UPLOAD_ROOT", tmp_path)
    files = {}
    for field, filename, _purpose in DATASETS:
        columns = required_columns("cmc", filename)
        if filename == "students.csv":
            columns = [column for column in columns if column != "Cohort"]
        files[field] = (filename, (",".join(columns) + "\n").encode(), "text/csv")

    response = client.post("/api/v1/uploads?institution=cmc", files=files)

    assert response.status_code == 422
    assert "students.csv is missing Cohort." in response.json()["error"]["message"]
    assert not (tmp_path / "cmc" / "students.csv").exists()


def test_a_complete_upload_is_what_the_dashboard_reads(client, monkeypatch, tmp_path) -> None:
    """All four files replace the synthetic set, and restore puts it back."""
    monkeypatch.setattr(data, "UPLOAD_ROOT", tmp_path)
    files = {}
    for field, filename, _purpose in DATASETS:
        columns = required_columns("cmc", filename)
        files[field] = (filename, (",".join(columns) + "\n").encode(), "text/csv")

    saved = client.post("/api/v1/uploads?institution=cmc", files=files)
    dashboard = client.get("/api/v1/dashboard?institution=cmc&credit_threshold=6")
    students = next(row for row in dashboard.json()["summary"] if row["id"] == "students")

    assert saved.status_code == 200
    assert dashboard.json()["using_upload"] is True
    assert students["value"] == 0

    restored = client.delete("/api/v1/uploads?institution=cmc")
    again = client.get("/api/v1/dashboard?institution=cmc&credit_threshold=6")
    students_again = next(row for row in again.json()["summary"] if row["id"] == "students")
    assert restored.status_code == 200
    assert again.json()["using_upload"] is False
    # Some synthetic rows are out of scope (non-credit), so expect a non-empty subset of the 1,000.
    assert 0 < students_again["value"] <= 1000
