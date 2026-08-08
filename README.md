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

## Webhook URL 설정(필수)

문서를 실제로 변환하려면 한컴 SDK에서 발급한 API 키와 외부에서 접근 가능한 HTTPS webhook URL이 **모두 필요합니다**. API 키, 원본 문서, 변환 결과는 저장소에 추가하지 마세요.

### 1. 이미 공개 HTTPS webhook 주소가 있는 경우

운영 중인 webhook 주소가 있다면 환경 변수로 전달하는 방법이 가장 간단합니다. `HancomDataLoader`는 명시적인 `webhook_url` 인수가 없을 때 `HANCOM_WEBHOOK_URL`을 자동으로 사용합니다.

```powershell
$env:HANCOM_API_KEY = "your-api-key"
$env:HANCOM_WEBHOOK_URL = "https://webhook.example.com/hancom/webhook"
```

```python
import os

from langchain_hancom_loader import HancomDataLoader

loader = HancomDataLoader(
    "./document.hwpx",
    api_key=os.environ["HANCOM_API_KEY"],
    mode="elements",
)
```

macOS와 Linux에서는 같은 값을 `export HANCOM_API_KEY=...`, `export HANCOM_WEBHOOK_URL=...`로 설정합니다. 코드에서만 URL을 지정하고 싶다면 `HancomDataLoader(..., webhook_url="https://...")`도 사용할 수 있습니다.

### 2. 공개 HTTPS webhook 주소가 없는 경우(개발·테스트)

공개 주소가 아직 없다면 아래 Compose 구성을 사용하세요. 로컬 수신기와 Cloudflare Quick Tunnel이 함께 시작되고, tunnel 컨테이너가 생성한 URL을 `.runtime/hancom-webhook.env`에 직접 기록합니다. Windows, macOS, Linux에서 같은 명령을 사용합니다.

```bash
docker compose -f deploy/compose.webhook.yaml up -d --build --wait
```

Compose 구성은 다음 작업을 자동으로 수행합니다.

1. `deploy/compose.webhook.yaml`로 webhook 수신기를 빌드하고 실행합니다.
2. tunnel 컨테이너가 Cloudflare Quick Tunnel을 시작해 임시 `https://...trycloudflare.com` 주소를 만듭니다.
3. 컨테이너가 최종 콜백 주소에 `/hancom/webhook`을 붙여 `.runtime/hancom-webhook.env`에 저장합니다.
4. `--wait`가 URL 파일이 준비될 때까지 기다린 뒤 명령을 끝냅니다.

생성된 주소는 다음 명령으로 확인할 수 있습니다.

```bash
docker compose -f deploy/compose.webhook.yaml exec -T tunnel \
  python -c "from pathlib import Path; print(Path('/runtime/hancom-webhook.env').read_text(), end='')"
```

호스트에서도 `.runtime/hancom-webhook.env` 파일을 직접 열어 같은 주소를 확인할 수 있습니다. 저장소 루트에서 Python을 실행하면 `HancomDataLoader`가 이 파일을 자동으로 읽습니다. 따라서 개발·테스트 코드에서는 `webhook_url`을 생략할 수 있습니다. 이 파일보다 `HANCOM_WEBHOOK_URL` 환경 변수가 우선합니다.

```python
import os

from langchain_hancom_loader import HancomDataLoader

loader = HancomDataLoader(
    "./document.hwpx",
    api_key=os.environ["HANCOM_API_KEY"],
    mode="elements",
)
```

로컬 상태 확인과 종료 명령은 다음과 같습니다.

```bash
curl -i http://localhost:8000/healthz
docker compose -f deploy/compose.webhook.yaml down
```

기본 `8000` 포트가 이미 사용 중이면 다른 포트를 지정할 수 있습니다.

```bash
export HANCOM_WEBHOOK_PORT=8012  # macOS/Linux
docker compose -f deploy/compose.webhook.yaml up -d --build --wait
curl -i http://localhost:8012/healthz
```

PowerShell에서 포트를 바꿀 때는 `export` 대신 `$env:HANCOM_WEBHOOK_PORT = "8012"`를 사용한 뒤 같은 Compose 명령을 실행합니다.

Quick Tunnel 주소는 개발·테스트용 임시 주소입니다. 터널 컨테이너를 중지하거나 다시 만들면 주소가 바뀔 수 있으므로 Compose 명령을 다시 실행해야 합니다. `docker compose down`으로 tunnel을 종료하면 만료된 `.runtime/hancom-webhook.env`도 자동으로 삭제됩니다. 터널과 webhook 컨테이너가 실행 중인 동안에만 외부 콜백을 받을 수 있습니다.

## Webhook 수신기 수동 실행과 운영 설정

로컬 수신기만 직접 실행하려면 다음 명령을 사용합니다.

```bash
hancom-webhook-receiver --port 8000
# 또는 python -m langchain_hancom_loader.webhook --port 8000
```

`GET /healthz`는 상태 확인용으로 `204 No Content`를 반환하고, `POST /hancom/webhook`은 JSON 객체 콜백만 받아 `204 No Content`를 반환합니다. 기본 설정에서는 콜백 본문을 저장하지 않습니다.

운영에서는 Quick Tunnel 대신 직접 관리하는 공개 HTTPS 주소를 준비해야 합니다. 운영 도메인의 리버스 프록시 또는 Ingress가 수신기의 `8000` 포트와 `/hancom/webhook` 경로로 요청을 전달하도록 설정한 뒤, 그 주소를 `webhook_url`에 명시적으로 넣습니다.

```python
webhook_url = "https://webhook.example.com/hancom/webhook"
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
- 개발용 자동 연결 URL은 `.runtime/hancom-webhook.env`에 저장되며 Git에서 제외됩니다. 다른 위치의 파일을 사용하려면 `HANCOM_WEBHOOK_ENV_FILE`에 경로를 설정합니다.
- 변환 API는 비동기 작업입니다. 로더는 완료 상태를 폴링한 뒤 결과를 LangChain 문서로 변환합니다.
- 내장 webhook 수신기는 유효한 콜백을 기본적으로 저장하지 않습니다. 저장 기능은 연동 진단 목적으로만 사용하세요.
- Cloudflare Quick Tunnel은 개발·테스트 전용입니다. 운영에서는 고정 도메인과 접근 정책을 적용한 webhook 주소를 명시적으로 전달하세요.
- 문서 구조를 보존하는 결과라도 모든 문서에서 검색·답변의 정확성을 보장하지는 않습니다. 실제 적용 전에는 입력 문서와 질문으로 결과를 검토하세요.
