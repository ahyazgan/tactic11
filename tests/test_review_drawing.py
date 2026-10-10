"""Drawing validation, privacy and PDF/portable report evidence."""
from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from app.reports import review_drawing
from app.reports.review_document import Drawing
from tests.test_match_reports import approve, create, document, headers, save, upload
from tests.test_match_reports import environment as environment


def drawing():
    return {"time": 1.5, "marks": [{"kind": "arrow", "color": "yellow", "x1": .2, "y1": .2, "x2": .8, "y2": .7}]}


@pytest.mark.parametrize("change", [
    {"time": .9}, {"time": 3}, {"time": float("inf")},
    {"marks": [{"kind": "arrow", "x1": -1, "x2": .3, "y1": .2, "y2": .4}]},
    {"marks": drawing()["marks"] * 21},
    {"marks": [{**drawing()["marks"][0], "color": "url(evil)"}]},
])
def test_invalid_drawing_cannot_enter_approved_report(environment, monkeypatch, change):
    client, _, _ = environment
    report = create(client, upload(client, monkeypatch))
    doc = document()
    doc["findings"][0]["drawing"] = {**drawing(), **change}
    # JSON can't encode infinity; send its JSON spelling directly to validation.
    import json
    response = client.put(f"/match-reports/{report['id']}", headers={**headers(), "Content-Type": "application/json"},
                          content=json.dumps({"version": 1, "title": report["title"], "document": doc}))
    assert response.status_code == 422


def test_saved_drawing_is_in_pdf_and_other_club_cannot_get_frame(environment, monkeypatch):
    client, _, _ = environment
    video = upload(client, monkeypatch)
    report = create(client, video)
    image = Image.new("RGB", (320, 180), "green")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    monkeypatch.setattr(review_drawing, "source_frame", lambda source, time: buffer.getvalue())
    frame_url = f"/match-reports/videos/{video['id']}/frame?at=1.5"
    assert client.get(frame_url, headers=headers("beta")).status_code == 404
    assert client.get(frame_url).status_code == 401
    assert client.get(frame_url, headers=headers()).headers["content-type"] == "image/png"
    assert client.get(frame_url.replace("1.5", "30"), headers=headers()).status_code == 422
    doc = document()
    doc["findings"][0]["drawing"] = drawing()
    saved = save(client, report, doc).json()
    assert saved["document"]["findings"][0]["drawing"] == drawing()
    approved = approve(client, saved)
    pdf = client.get(f"/match-reports/{approved['id']}/pdf", headers=headers())
    assert pdf.status_code == 200 and b"/Subtype /Image" in pdf.content
    # Drawing is in normalized coordinates, and really changes the source pixels.
    annotated = Image.open(BytesIO(review_drawing.draw_frame(buffer.getvalue(), Drawing.model_validate(drawing()))))
    assert annotated.getpixel((64, 36)) != image.getpixel((64, 36))
