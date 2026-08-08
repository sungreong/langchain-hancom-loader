# LangChain Hancom Loader

`langchain-hancom-loader`는 한컴 데이터 로더 API로 HWP, HWPX, PDF 문서를 구조화된 AIJSON으로 변환한 뒤 LangChain `Document` 목록으로 반환하는 Python 패키지입니다. 일반 LangChain 로더처럼 `load()` 또는 `lazy_load()`를 사용할 수 있습니다.

## 설치

Python 3.10 이상이 필요합니다. 저장소를 복제한 뒤 패키지 루트에서 설치합니다.

```bash
git clone https://github.com/sungreong/langchain-hancom-loader.git
cd langchain-hancom-loader
python -m pip install .
```

설치 후 프로젝트 폴더 밖에서 공개 API를 확인할 수 있습니다.

```bash
cd ..
python -c "from langchain_hancom_loader import HancomDataLoader; print(HancomDataLoader.__name__)"
```

## 사용 전 준비

문서를 실제로 변환하려면 한컴 SDK에서 발급한 API 키와 외부에서 접근 가능한 HTTPS webhook URL이 필요합니다. API 키, 원본 문서, 변환 결과는 저장소에 추가하지 마세요.

PowerShell에서는 API 키를 다음처럼 설정합니다.

```powershell
$env:HANCOM_API_KEY = "your-api-key"
```

## Webhook 수신기 설정(선택)

한컴 데이터 로더 API는 외부에서 접근 가능한 HTTPS webhook URL을 사용합니다. 이 패키지는 완료 콜백을 수신해 정상 응답하는 작은 수신기를 함께 제공합니다. 로더는 변환 상태를 직접 폴링하므로, 수신기는 콜백을 확인하거나 운영 환경의 webhook URL을 구성할 때 사용하면 됩니다.

로컬 또는 서버에서 수신기를 실행합니다.

```bash
hancom-webhook-receiver --port 8000
# 또는 python -m langchain_hancom_loader.webhook --port 8000
```

`GET /healthz`는 상태 확인용으로 `204 No Content`를 반환하고, `POST /hancom/webhook`은 JSON 객체 콜백만 받아 `204 No Content`를 반환합니다. 기본 설정에서는 콜백 본문을 저장하지 않습니다.

Docker Compose로 실행하려면 저장소를 복제한 뒤 다음 명령을 사용합니다.

```bash
docker compose -f deploy/compose.webhook.yaml up -d --build
curl http://localhost:8000/healthz
```

공개 HTTPS 주소는 직접 준비해야 합니다. 운영 도메인의 리버스 프록시 또는 Ingress가 컨테이너의 `8000` 포트와 `/hancom/webhook` 경로로 요청을 전달하도록 설정한 뒤, 그 주소를 `webhook_url`에 넣습니다.

```python
webhook_url = "https://example.com/hancom/webhook"
```

연동을 진단할 때만 `--output-dir`로 콜백 본문을 저장할 수 있습니다. 콜백에 작업 정보가 포함될 수 있으므로 저장 경로는 Git으로 추적하지 말고, 확인 후 삭제하거나 접근을 제한하세요.

```bash
hancom-webhook-receiver --port 8000 --output-dir ./webhook-events
```

## 최소 사용 예시

```python
import os

from langchain_hancom_loader import HancomDataLoader

loader = HancomDataLoader(
    "./document.hwpx",
    api_key=os.environ["HANCOM_API_KEY"],
    webhook_url="https://example.com/hancom/webhook",
    mode="elements",
)

documents = loader.load()
for document in documents:
    print(document.page_content)
    print(document.metadata)
```

`HancomDataLoader`는 LangChain `BaseLoader`를 상속합니다. 따라서 `load()`, `lazy_load()`, `aload()`, `alazy_load()`를 사용할 수 있으며, 반환값은 LangChain `Document`입니다.

기본 `elements` 모드는 AIJSON 요소마다 하나의 `Document`를 반환합니다. `mode="paged"`는 페이지별 문서를, `mode="single"`은 전체 문서 하나를 반환합니다. 요소 모드의 메타데이터에는 문서·페이지·요소 식별자와 종류, 위치 좌표처럼 검색 근거를 확인하는 데 쓸 수 있는 정보가 포함됩니다.

## 오류 처리

```python
from langchain_hancom_loader import (
    HancomAPIError,
    HancomConversionError,
    HancomJobTimeoutError,
)

try:
    documents = loader.load()
except HancomJobTimeoutError:
    # 변환 상태와 timeout 설정을 확인합니다.
    raise
except HancomConversionError:
    # 지원 형식, 문서 상태, API error_code를 확인합니다.
    raise
except HancomAPIError:
    # API 키, 크레딧, 네트워크, API 응답을 확인합니다.
    raise
```

현재 구현은 HWP, HWPX, PDF와 파일당 최대 100MB를 입력 검증합니다. 최신 API 정책과 지원 범위는 [한컴 데이터 로더 공식 페이지](https://sdk.hancom.com/services/1?type=DATA_LOADER)에서 확인하세요.

## 보안과 제한 사항

- `HANCOM_API_KEY`와 `webhook_url`은 실행 환경에서 전달합니다.
- 변환 API는 비동기 작업입니다. 로더는 완료 상태를 폴링한 뒤 결과를 LangChain 문서로 변환합니다.
- 내장 webhook 수신기는 유효한 콜백을 기본적으로 저장하지 않습니다. 저장 기능은 연동 진단 목적으로만 사용하세요.
- 문서 구조를 보존하는 결과라도 모든 문서에서 검색·답변의 정확성을 보장하지는 않습니다. 실제 적용 전에는 입력 문서와 질문으로 결과를 검토하세요.
