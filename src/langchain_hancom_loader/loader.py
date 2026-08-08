"""LangChain loader for the Hancom Data Loader asynchronous conversion API."""

from __future__ import annotations

import json
import mimetypes
import os
import time
from collections import defaultdict
from collections.abc import Iterator, Mapping
from html import escape
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document
from markdown import markdown

_DEFAULT_BASE_URL = "https://api.sdk.hancom.com/api/api-services"
_SUPPORTED_SUFFIXES = {".hwp", ".hwpx", ".pdf"}
_MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024


class HancomDataLoaderError(RuntimeError):
    """Base exception for Hancom Data Loader integration failures."""


class HancomAPIError(HancomDataLoaderError):
    """Raised when the Hancom API rejects a request or returns an invalid response."""


class HancomConversionError(HancomDataLoaderError):
    """Raised when a submitted document conversion fails."""


class HancomJobTimeoutError(HancomDataLoaderError):
    """Raised when a conversion does not finish before the configured timeout."""


class HancomDataLoader(BaseLoader):
    """Convert a document with Hancom Data Loader and return LangChain documents.

    The API conversion is asynchronous. Calling :meth:`load` uploads ``file_path``,
    polls the job until it is complete, downloads the resulting aijson payload, and
    maps it to LangChain ``Document`` instances.

    Args:
        file_path: Local HWP, HWPX, or PDF file to convert.
        api_key: Hancom API key. Defaults to the ``HANCOM_API_KEY`` environment
            variable.
        mode: ``"elements"`` returns one document per aijson element,
            ``"paged"`` returns one document per page, and ``"single"`` returns
            one document for the entire input.
        webhook_url: Public URL to receive the API completion callback. Defaults to
            the ``HANCOM_WEBHOOK_URL`` environment variable. The API requires this
            URL even though this loader polls for the completed result.
        poll_interval: Seconds to wait between status checks.
        timeout: Maximum seconds to wait for a conversion to complete.
        request_timeout: Per-request HTTP timeout in seconds.
        base_url: API base URL, primarily useful for testing or a compatible proxy.
        client: Optional ``httpx.Client``. The caller owns its lifecycle.
        save_aijson_to: Optional path to save the downloaded aijson result before
            it is converted into LangChain documents.
        export_to: Optional directory for a page-by-page archive. The loader writes
            an index and one file per page after conversion.
        export_format: Archive format: ``"markdown"``, ``"html"``, or ``"both"``.
    """

    def __init__(
        self,
        file_path: str | Path,
        *,
        api_key: str | None = None,
        mode: Literal["elements", "paged", "single"] = "elements",
        webhook_url: str | None = None,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
        request_timeout: float = 30.0,
        base_url: str = _DEFAULT_BASE_URL,
        client: httpx.Client | None = None,
        save_aijson_to: str | Path | None = None,
        export_to: str | Path | None = None,
        export_format: Literal["markdown", "html", "both"] = "markdown",
    ) -> None:
        self.file_path = Path(file_path)
        self.api_key = api_key or os.environ.get("HANCOM_API_KEY")
        self.mode = mode
        self.webhook_url = webhook_url or os.environ.get("HANCOM_WEBHOOK_URL")
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.request_timeout = request_timeout
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.save_aijson_to = Path(save_aijson_to) if save_aijson_to else None
        self.export_to = Path(export_to) if export_to else None
        self.export_format = export_format
        self._validate_configuration()

    def lazy_load(self) -> Iterator[Document]:
        """Yield LangChain documents after the conversion result is available."""
        with self._get_client() as client:
            history_id = self._submit_conversion(client)
            status = self._wait_for_completion(client, history_id)
            payload = self._download_result(client, history_id, status)

        if self.save_aijson_to:
            self._save_aijson(payload)
        parsed_elements, source_metadata = self._parse_aijson(payload)
        if self.export_to:
            self._export_pages(parsed_elements, source_metadata)
        yield from self._documents_from_elements(parsed_elements, source_metadata)

    def _validate_configuration(self) -> None:
        if not self.api_key:
            raise ValueError(
                "Hancom API key is required. Pass api_key or set HANCOM_API_KEY."
            )
        if not self.webhook_url:
            raise ValueError(
                "Hancom webhook URL is required. Pass webhook_url or set "
                "HANCOM_WEBHOOK_URL."
            )
        if self.mode not in {"elements", "paged", "single"}:
            raise ValueError("mode must be one of: elements, paged, single.")
        if self.export_format not in {"markdown", "html", "both"}:
            raise ValueError("export_format must be one of: markdown, html, both.")
        if self.poll_interval <= 0:
            raise ValueError("poll_interval must be greater than zero.")
        if self.timeout <= 0 or self.request_timeout <= 0:
            raise ValueError("timeout and request_timeout must be greater than zero.")
        self._validate_http_url(self.webhook_url, "webhook_url")
        self._validate_http_url(self.base_url, "base_url")
        if not self.file_path.is_file():
            raise FileNotFoundError(f"Document file does not exist: {self.file_path}")
        if self.file_path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            supported = ", ".join(sorted(_SUPPORTED_SUFFIXES))
            raise ValueError(f"Unsupported file type. Expected one of: {supported}.")
        if self.file_path.stat().st_size > _MAX_FILE_SIZE_BYTES:
            raise ValueError("Document size must not exceed 100 MB.")
        if self.file_path.stat().st_size == 0:
            raise ValueError("Document file must not be empty.")

    @staticmethod
    def _validate_http_url(value: str, field_name: str) -> None:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"{field_name} must be an absolute HTTP or HTTPS URL.")
        try:
            _ = parsed.port
        except ValueError as error:
            raise ValueError(f"{field_name} must include a valid numeric port.") from error

    def _get_client(self) -> httpx.Client:
        if self.client is not None:
            return _BorrowedClient(self.client)
        return httpx.Client(timeout=self.request_timeout)

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key or ""}

    def _submit_conversion(self, client: httpx.Client) -> int:
        mime_type = mimetypes.guess_type(self.file_path.name)[0] or "application/octet-stream"
        data = {"webhook_url": self.webhook_url}

        try:
            with self.file_path.open("rb") as document_file:
                response = client.post(
                    f"{self.base_url}/convert",
                    headers=self._headers(),
                    data=data,
                    files={"file": (self.file_path.name, document_file, mime_type)},
                )
            payload = self._response_json(response, "submit conversion")
        except httpx.HTTPError as error:
            raise HancomAPIError(f"Could not submit conversion: {error}") from error

        data_payload = self._success_data(payload, "submit conversion")
        history_id = data_payload.get("api_history_id")
        if not isinstance(history_id, int):
            raise HancomAPIError("Conversion response did not include api_history_id.")
        return history_id

    def _wait_for_completion(
        self, client: httpx.Client, history_id: int
    ) -> Mapping[str, Any]:
        deadline = time.monotonic() + self.timeout
        while True:
            status = self._get_status(client, history_id)
            state = status.get("status")
            if state == "DONE":
                return status
            if state == "FAILED":
                reason = status.get("message") or "The conversion failed."
                error_code = status.get("error_code")
                detail = f"{error_code}: {reason}" if error_code else str(reason)
                raise HancomConversionError(detail)
            if state not in {"PENDING", "PROCESSING"}:
                raise HancomAPIError(f"Unknown conversion status: {state!r}.")
            if time.monotonic() >= deadline:
                raise HancomJobTimeoutError(
                    f"Conversion {history_id} did not finish within {self.timeout} seconds."
                )
            time.sleep(min(self.poll_interval, max(0.0, deadline - time.monotonic())))

    def _get_status(self, client: httpx.Client, history_id: int) -> Mapping[str, Any]:
        try:
            response = client.get(
                f"{self.base_url}/status/{history_id}", headers=self._headers()
            )
            payload = self._response_json(response, "retrieve conversion status")
        except httpx.HTTPError as error:
            raise HancomAPIError(f"Could not retrieve conversion status: {error}") from error
        return self._success_data(payload, "retrieve conversion status")

    def _download_result(
        self,
        client: httpx.Client,
        history_id: int,
        status: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        download_url = status.get("download_url")
        url = (
            download_url
            if isinstance(download_url, str)
            else f"{self.base_url}/download/{history_id}"
        )
        try:
            self._validate_http_url(url, "download_url")
        except ValueError as error:
            raise HancomAPIError("Conversion status included an invalid download_url.") from error

        # A status response may theoretically point at a pre-signed object-storage URL.
        # Never forward the Hancom API key to a different origin.
        headers = self._headers() if self._same_origin(url, self.base_url) else {}
        try:
            response = client.get(url, headers=headers)
            payload = self._response_json(response, "download conversion result")
        except httpx.HTTPError as error:
            raise HancomAPIError(f"Could not download conversion result: {error}") from error
        if not isinstance(payload, Mapping):
            raise HancomAPIError("Downloaded conversion result must be a JSON object.")
        return payload

    @staticmethod
    def _same_origin(left: str, right: str) -> bool:
        def origin(url: str) -> tuple[str, str | None, int | None]:
            parsed = urlsplit(url)
            port = parsed.port
            if port is None:
                port = 443 if parsed.scheme == "https" else 80
            return parsed.scheme.lower(), parsed.hostname, port

        return origin(left) == origin(right)

    def _save_aijson(self, payload: Mapping[str, Any]) -> None:
        assert self.save_aijson_to is not None
        self.save_aijson_to.parent.mkdir(parents=True, exist_ok=True)
        self.save_aijson_to.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _response_json(response: httpx.Response, action: str) -> Any:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            detail = response.text[:500]
            raise HancomAPIError(
                f"Could not {action}: HTTP {response.status_code}. {detail}"
            ) from error
        try:
            return response.json()
        except json.JSONDecodeError as error:
            raise HancomAPIError(f"Could not {action}: response was not JSON.") from error

    @staticmethod
    def _success_data(payload: Any, action: str) -> Mapping[str, Any]:
        if not isinstance(payload, Mapping):
            raise HancomAPIError(f"Could not {action}: response was not a JSON object.")
        if payload.get("success") is not True:
            message = payload.get("message") or "The API reported an unsuccessful request."
            error_code = payload.get("error_code")
            detail = f"{error_code}: {message}" if error_code else str(message)
            raise HancomAPIError(f"Could not {action}: {detail}")
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise HancomAPIError(f"Could not {action}: response did not include data.")
        return data

    def _parse_aijson(
        self, payload: Mapping[str, Any]
    ) -> tuple[list[Document], dict[str, Any]]:
        elements = payload.get("elements")
        metadata = payload.get("metadata")
        if not isinstance(elements, list):
            raise HancomAPIError("aijson result did not include an elements array.")
        if not isinstance(metadata, Mapping):
            metadata = {}

        file_name = metadata.get("fileName")
        if not isinstance(file_name, str) or not file_name:
            file_name = self.file_path.name
        file_format = metadata.get("format")
        if not isinstance(file_format, str) or not file_format:
            file_format = self.file_path.suffix.lstrip(".").upper()

        source_metadata: dict[str, Any] = {
            "source": str(self.file_path.resolve()),
            "file_name": file_name,
            "file_format": file_format,
        }
        version = payload.get("version")
        if self._is_scalar_metadata(version):
            source_metadata["hancom_aijson_version"] = version
        page_count = metadata.get("numOfPages")
        if isinstance(page_count, int) and not isinstance(page_count, bool) and page_count >= 0:
            source_metadata["page_count"] = page_count

        parsed_elements = []
        for index, element in enumerate(elements):
            if not isinstance(element, Mapping):
                raise HancomAPIError(
                    f"aijson element at index {index} must be a JSON object."
                )
            parsed_elements.append(self._parse_element(element, source_metadata, index))
        return parsed_elements, source_metadata

    def _documents_from_elements(
        self, parsed_elements: list[Document], source_metadata: Mapping[str, Any]
    ) -> Iterator[Document]:
        if not parsed_elements:
            return
        if self.mode == "elements":
            yield from parsed_elements
            return

        if self.mode == "paged":
            for page_index, page_documents in self._group_by_page(parsed_elements):
                metadata = dict(source_metadata)
                metadata["element_count"] = len(page_documents)
                if page_index is None:
                    metadata["unpaged"] = True
                else:
                    metadata.update({"page": page_index + 1, "page_index": page_index})
                yield Document(
                    page_content="\n\n".join(item.page_content for item in page_documents),
                    metadata=metadata,
                )
            return

        metadata = dict(source_metadata)
        metadata["element_count"] = len(parsed_elements)
        yield Document(
            page_content="\n\n".join(item.page_content for item in parsed_elements),
            metadata=metadata,
        )

    def _export_pages(
        self, parsed_elements: list[Document], source_metadata: Mapping[str, Any]
    ) -> None:
        assert self.export_to is not None
        self.export_to.mkdir(parents=True, exist_ok=True)
        pages = self._group_by_page(parsed_elements)
        title = str(source_metadata.get("file_name", self.file_path.name))

        if self.export_format in {"markdown", "both"}:
            self._write_markdown_archive(pages, title)
        if self.export_format in {"html", "both"}:
            self._write_html_archive(pages, title)

    @staticmethod
    def _group_by_page(parsed_elements: list[Document]) -> list[tuple[int | None, list[Document]]]:
        by_page: dict[int, list[Document]] = defaultdict(list)
        unpaged: list[Document] = []
        for document in parsed_elements:
            page_index = document.metadata.get("page_index")
            if isinstance(page_index, int):
                by_page[page_index].append(document)
            else:
                unpaged.append(document)

        pages = [(page_index, by_page[page_index]) for page_index in sorted(by_page)]
        if unpaged:
            pages.append((None, unpaged))
        return pages

    def _write_markdown_archive(
        self, pages: list[tuple[int | None, list[Document]]], title: str
    ) -> None:
        pages_dir = self.export_to / "markdown"
        pages_dir.mkdir(parents=True, exist_ok=True)
        index_lines = [f"# {title}", ""]

        for page_index, documents in pages:
            page_label = self._page_label(page_index)
            filename = self._page_filename(page_index, "md")
            content = self._page_content(documents)
            (pages_dir / filename).write_text(
                f"# {title} - {page_label}\n\n{content}\n",
                encoding="utf-8",
            )
            index_lines.append(f"- [{page_label}](markdown/{filename})")

        (self.export_to / "index.md").write_text(
            "\n".join(index_lines) + "\n", encoding="utf-8"
        )

    def _write_html_archive(
        self, pages: list[tuple[int | None, list[Document]]], title: str
    ) -> None:
        pages_dir = self.export_to / "html"
        pages_dir.mkdir(parents=True, exist_ok=True)
        links = []

        for position, (page_index, documents) in enumerate(pages):
            page_label = self._page_label(page_index)
            filename = self._page_filename(page_index, "html")
            links.append(f'<li><a href="html/{filename}">{escape(page_label)}</a></li>')
            previous_link = ""
            next_link = ""
            if position > 0:
                previous_filename = self._page_filename(pages[position - 1][0], "html")
                previous_link = f'<a href="{previous_filename}">Previous</a>'
            if position < len(pages) - 1:
                next_filename = self._page_filename(pages[position + 1][0], "html")
                next_link = f'<a href="{next_filename}">Next</a>'
            page_html = markdown(
                escape(self._page_content(documents)),
                extensions=["tables", "fenced_code"],
            )
            (pages_dir / filename).write_text(
                self._html_document(
                    f"{title} - {page_label}",
                    f'<nav><a href="../index.html">Index</a> {previous_link} {next_link}</nav>'
                    f"<main><h1>{escape(title)} - {escape(page_label)}</h1>{page_html}</main>",
                ),
                encoding="utf-8",
            )

        index_body = f"<main><h1>{escape(title)}</h1><ol>{''.join(links)}</ol></main>"
        (self.export_to / "index.html").write_text(
            self._html_document(title, index_body), encoding="utf-8"
        )

    @staticmethod
    def _page_content(documents: list[Document]) -> str:
        return "\n\n".join(document.page_content for document in documents)

    @staticmethod
    def _page_label(page_index: int | None) -> str:
        return f"Page {page_index + 1}" if page_index is not None else "Unpaged content"

    @staticmethod
    def _page_filename(page_index: int | None, suffix: str) -> str:
        if page_index is None:
            return f"unpaged.{suffix}"
        return f"page-{page_index + 1:03d}.{suffix}"

    @staticmethod
    def _html_document(title: str, body: str) -> str:
        return (
            "<!doctype html>\n"
            "<html lang=\"en\">\n"
            "<head><meta charset=\"utf-8\"><title>"
            f"{escape(title)}"
            "</title></head>\n"
            f"<body>{body}</body>\n"
            "</html>\n"
        )

    @staticmethod
    def _parse_element(
        element: Mapping[str, Any],
        source_metadata: Mapping[str, Any],
        element_index: int,
    ) -> Document:
        content = element.get("content")
        content = content if isinstance(content, Mapping) else {}
        markdown_content = content.get("markdown")
        text_content = content.get("text")
        if isinstance(markdown_content, str) and markdown_content:
            text = markdown_content
        elif isinstance(text_content, str):
            text = text_content
        else:
            text = ""
        category = element.get("category")
        category = category if isinstance(category, Mapping) else {}
        page_index = element.get("pageIndex")
        element_metadata: dict[str, Any] = dict(source_metadata)
        element_metadata["element_index"] = element_index
        for key, value in (
            ("element_id", element.get("id")),
            ("category", category.get("label")),
            ("category_type", category.get("type")),
            ("confidence", element.get("confidence")),
        ):
            if HancomDataLoader._is_scalar_metadata(value):
                element_metadata[key] = value

        bbox = element.get("bbox")
        if isinstance(bbox, Mapping):
            for coordinate in ("left", "top", "width", "height"):
                value = bbox.get(coordinate)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    element_metadata[f"bbox_{coordinate}"] = value

        if isinstance(page_index, int) and not isinstance(page_index, bool) and page_index >= 0:
            element_metadata["page"] = page_index + 1
            element_metadata["page_index"] = page_index
        return Document(page_content=str(text), metadata=element_metadata)

    @staticmethod
    def _is_scalar_metadata(value: object) -> bool:
        """Return whether a value is portable across common vector stores."""
        return isinstance(value, (str, int, float, bool))


class _BorrowedClient:
    """Do not close an HTTP client supplied by the caller."""

    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def __enter__(self) -> httpx.Client:
        return self.client

    def __exit__(self, *args: object) -> None:
        return None
