from __future__ import annotations

from pathlib import Path

from langchain_hancom_loader import HancomDataLoader


def test_maps_legacy_hwp_aijson_body_and_table_metadata(tmp_path: Path) -> None:
    input_path = tmp_path / "sample.hwpx"
    input_path.write_bytes(b"placeholder")
    loader = HancomDataLoader(
        input_path,
        api_key="test-key",
        webhook_url="https://example.test/hancom/webhook",
    )
    payload = {
        "documentPr": {"aiJsonVer": "1.0", "fileExt": "hwpx", "title": "Sample"},
        "body": [
            {
                "clientInfo": {"parentType": "body"},
                "posInfo": {"listId": 0, "paraId": 3, "docPageNum": 1},
                "contents": {"text": "A paragraph"},
                "inferenceInfo": {"inferenceType": "bodypara", "inferenceLevel": 1},
            },
            {
                "clientInfo": {
                    "parentType": "table",
                    "parentObjectName": "t0",
                    "rowAddr": 2,
                    "colAddr": 1,
                    "rowSpan": 1,
                    "colSpan": 2,
                },
                "posInfo": {"listId": 5, "paraId": 0, "docPageNum": 1},
                "contents": {"text": "Merged cell"},
                "inferenceInfo": {"inferenceType": "none"},
            },
        ],
    }

    parsed, metadata = loader._parse_aijson(payload)
    documents = list(loader._documents_from_elements(parsed, metadata))

    assert [document.page_content for document in documents] == [
        "A paragraph",
        "Merged cell",
    ]
    assert documents[0].metadata["file_format"] == "HWPX"
    assert documents[0].metadata["hancom_aijson_schema"] == "legacy_hwp"
    assert documents[0].metadata["page"] == 1
    assert documents[1].metadata["category"] == "table"
    assert documents[1].metadata["parent_object_name"] == "t0"
    assert documents[1].metadata["table_row"] == 2
    assert documents[1].metadata["table_column_span"] == 2
