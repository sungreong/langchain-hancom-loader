# Changelog

## Unreleased

- Docker Compose의 tunnel 컨테이너가 Cloudflare Quick Tunnel을 시작하고 생성된 공개 HTTPS 주소를 직접 기록하도록 구성했습니다. 호스트 운영체제와 관계없이 Compose 명령으로 실행할 수 있습니다.
- 생성된 webhook URL을 `.runtime/hancom-webhook.env`에 저장하고, 사용자가 실제 생성 주소를 애플리케이션의 `HANCOM_WEBHOOK_URL` 환경 변수에 명시적으로 전달하도록 안내합니다.
- `hancom-webhook-url` 명령으로 Compose가 생성한 webhook 환경 변수 항목을 한 줄로 출력할 수 있습니다.

## 0.1.0 - 2026-08-08

- 한컴 데이터 로더 API의 비동기 변환 결과를 LangChain `Document`로 변환하는 `HancomDataLoader`를 추가했습니다.
- 요소·페이지·단일 문서 모드와 원본 요소 메타데이터를 지원합니다.
- API 응답, 변환 실패, 시간 초과를 구분하는 예외를 제공합니다.
- 외부 HTTPS 환경에 배포할 수 있는 선택형 webhook 수신기와 Docker Compose 실행 예시를 추가했습니다.
- 콜백 본문 저장을 기본 비활성화하고, 진단 시에만 `--output-dir`로 저장하도록 했습니다.
