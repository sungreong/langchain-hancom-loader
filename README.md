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
- 문서 구조를 보존하는 결과라도 모든 문서에서 검색·답변의 정확성을 보장하지는 않습니다. 실제 적용 전에는 입력 문서와 질문으로 결과를 검토하세요.
