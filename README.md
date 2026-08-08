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

운영 중인 webhook 주소가 있다면 애플리케이션 실행 환경에 아래 두 값을 설정합니다. `https://webhook.example.com/...`은 사용자가 이미 보유한 고정 공개 URL의 예시입니다. `HancomDataLoader`는 명시적인 `webhook_url` 인수가 없을 때 `HANCOM_WEBHOOK_URL`을 사용합니다.

```dotenv
HANCOM_API_KEY=your-api-key
HANCOM_WEBHOOK_URL=https://webhook.example.com/hancom/webhook
```

```python
import os

from langchain_hancom_loader import HancomDataLoader

loader = HancomDataLoader(
    "./document.hwpx",
    api_key=os.environ["HANCOM_API_KEY"],
    webhook_url=os.environ["HANCOM_WEBHOOK_URL"],
    mode="elements",
)
```

이 값은 Docker Compose의 `environment`, 배포 서비스의 Secret, IDE 실행 구성, CI 환경 변수처럼 사용하는 실행 환경의 방식으로 전달합니다. 위 예제처럼 `webhook_url`에 환경 변수 값을 명시적으로 전달할 수 있으며, 인수를 생략하면 `HancomDataLoader`가 `HANCOM_WEBHOOK_URL`을 자동으로 읽습니다. 코드에서만 URL을 지정하고 싶다면 `HancomDataLoader(..., webhook_url="https://...")`도 사용할 수 있습니다.

### 2. 공개 HTTPS webhook 주소가 없는 경우(개발·테스트)

개발자가 로컬에서 바로 테스트할 때는 공개 도메인을 만들 필요가 없습니다. 아래 Compose 구성이 로컬 수신기와 Cloudflare Quick Tunnel을 함께 시작하고, tunnel 컨테이너가 생성한 임시 공개 URL을 `.runtime/hancom-webhook.env`에 직접 기록합니다. Windows, macOS, Linux에서 같은 명령을 사용합니다.

```bash
docker compose -f deploy/compose.webhook.yaml up -d --build --wait
```

Compose 구성은 다음 작업을 자동으로 수행합니다.

1. `deploy/compose.webhook.yaml`로 webhook 수신기를 빌드하고 실행합니다.
2. tunnel 컨테이너가 Cloudflare Quick Tunnel을 시작해 임시 `https://...trycloudflare.com` 주소를 만듭니다.
3. 컨테이너가 최종 콜백 주소에 `/hancom/webhook`을 붙여 `.runtime/hancom-webhook.env`에 저장합니다.
4. `--wait`가 URL 파일이 준비될 때까지 기다린 뒤 명령을 끝냅니다.

`--wait`가 끝난 뒤 패키지 루트에서 아래 명령을 실행하면 **실제로 생성된** 콜백 URL이 환경 변수 형식으로 한 줄 출력됩니다. `hancom-webhook-url`은 패키지 설치 시 함께 제공되는 Windows, macOS, Linux 공통 명령입니다.

```bash
hancom-webhook-url
# HANCOM_WEBHOOK_URL=https://<이번 실행에서 생성된 주소>.trycloudflare.com/hancom/webhook
```

명령을 찾을 수 없는 Python 환경에서는 `python -m langchain_hancom_loader.webhook_url`로 같은 결과를 확인할 수 있습니다. 같은 값은 호스트의 `.runtime/hancom-webhook.env`에도 기록됩니다. 로더가 이 파일이나 로컬 포트를 자동으로 찾지는 않습니다. 출력된 한 줄을 복사해 **로더를 실행하는 애플리케이션의 환경 변수**에 넣어 연결합니다. URL만 필요하면 `hancom-webhook-url --value-only`를 사용하세요.

```dotenv
HANCOM_API_KEY=your-api-key
HANCOM_WEBHOOK_URL=https://<위 명령이 출력한 실제 주소>.trycloudflare.com/hancom/webhook
```

터널을 다시 시작하면 주소도 바뀌므로, 새로 출력된 값을 같은 위치에 교체한 뒤 애플리케이션을 다시 시작합니다. 이 환경 변수는 패키지 폴더가 아닌 실제 애플리케이션의 실행 환경에 설정해야 합니다.

```python
import os

from langchain_hancom_loader import HancomDataLoader

loader = HancomDataLoader(
    "./document.hwpx",
    api_key=os.environ["HANCOM_API_KEY"],
    webhook_url=os.environ["HANCOM_WEBHOOK_URL"],
    mode="elements",
)
```

로컬 상태 확인과 종료 명령은 다음과 같습니다.

```bash
curl -i http://localhost:8000/healthz
docker compose -f deploy/compose.webhook.yaml down
```

Quick Tunnel 주소는 개발·테스트용 임시 주소입니다. 터널 컨테이너를 중지하거나 다시 만들면 주소가 바뀔 수 있으므로 Compose 명령을 다시 실행해야 합니다. `docker compose down`으로 tunnel을 종료하면 만료된 `.runtime/hancom-webhook.env`도 자동으로 삭제됩니다. 터널과 webhook 컨테이너가 실행 중인 동안에만 외부 콜백을 받을 수 있습니다.

## 운영용 webhook 컨테이너

운영에서는 별도의 수신기 명령을 실행하지 않아도 됩니다. 패키지에 포함된 `Dockerfile.webhook`과 Compose 파일이 webhook 수신 컨테이너를 제공합니다. 다음 명령으로 컨테이너를 시작하세요.

```bash
docker compose -f deploy/compose.webhook.production.yaml up -d --build
```

컨테이너는 `8000` 포트에서 `POST /hancom/webhook`을 받고, 상태 확인에는 `GET /healthz`를 제공합니다. 이 운영 Compose 파일은 도메인을 자동으로 만들지 않습니다. `webhook.example.com`은 **운영자가 DNS와 HTTPS를 이미 연결한 도메인의 예시**입니다. 배포 환경의 HTTPS 도메인·Ingress·리버스 프록시가 이 컨테이너의 `8000` 포트와 `/hancom/webhook` 경로로 연결되도록 설정한 뒤, 그 공개 HTTPS 주소를 로더 애플리케이션의 환경 변수에 설정합니다.

```dotenv
# webhook.example.com은 실제 운영 도메인으로 교체합니다.
HANCOM_WEBHOOK_URL=https://webhook.example.com/hancom/webhook
```

로컬 개발·테스트라면 이 운영 Compose 파일을 쓰지 말고 위 Quick Tunnel 흐름을 사용하세요. 운영 Compose 파일은 webhook 컨테이너만 실행하며 TLS 인증서와 도메인 연결은 포함하지 않습니다. 이미 사용하는 클라우드 Load Balancer, Ingress 또는 리버스 프록시에서 HTTPS를 종료해 컨테이너로 전달하세요.

## 최소 사용 예시

```python
import os

from langchain_hancom_loader import HancomDataLoader

loader = HancomDataLoader(
    "./document.hwpx",
    api_key=os.environ["HANCOM_API_KEY"],
    webhook_url=os.environ["HANCOM_WEBHOOK_URL"],
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

- `HANCOM_API_KEY`와 `HANCOM_WEBHOOK_URL`은 실행 환경에서 전달합니다. 로더 생성 시 각각 `api_key`와 `webhook_url`에 명시적으로 넘길 수 있습니다.
- 개발용 Quick Tunnel URL은 `.runtime/hancom-webhook.env`에 저장되며 Git에서 제외됩니다. 해당 파일에서 확인한 실제 주소를 로더 애플리케이션의 `HANCOM_WEBHOOK_URL`에 명시적으로 설정하세요.
- 변환 API는 비동기 작업입니다. 로더는 완료 상태를 폴링한 뒤 결과를 LangChain 문서로 변환합니다.
- 내장 webhook 수신기는 유효한 콜백을 기본적으로 저장하지 않습니다. 저장 기능은 연동 진단 목적으로만 사용하세요.
- Cloudflare Quick Tunnel은 개발·테스트 전용입니다. 운영에서는 고정 도메인과 접근 정책을 적용한 webhook 주소를 명시적으로 전달하세요.
- 문서 구조를 보존하는 결과라도 모든 문서에서 검색·답변의 정확성을 보장하지는 않습니다. 실제 적용 전에는 입력 문서와 질문으로 결과를 검토하세요.
