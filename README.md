# Departure Ready MCP

출국 전에 꼭 한 번 하게 되는 질문을 공식 데이터 기준으로 정리해 주는 **공항 출발 준비 MCP + HTTP API** 프로젝트입니다.

이 프로젝트가 답하려는 질문은 단순합니다.
- 지금 공항으로 출발해도 되는지
- 차를 가져가도 괜찮은지
- 이 물건을 기내 반입하거나 위탁할 수 있는지
- 스마트패스, 셀프 체크인, 우대출구 같은 빠른 서비스를 쓸 수 있는지
- 터미널 안에서 약국, ATM, 환전소, 라운지 같은 시설이 어디 있는지

## 현재 지원 범위

- 강한 지원: `ICN`, `GMP`, `CJU`
- 선택 지원: `PUS`, `CJJ`, `TAE`
- 공식 시설/접근성 조회: `ICN`, `GMP`, `CJU`, `PUS`, `CJJ`, `TAE`
- 상점 조회: `ICN`만 지원
- 미래 날짜 항공편 조회: `ICN`만 지원하며 `/v1/flight-status`와 `tool_get_flight_status`에서만 공식 제공
- 원격 MCP 전송 방식: `/mcp`에 마운트된 `streamable-http`

HTTP 엔드포인트:
- `/healthz`
- `/v1/coverage`
- `/v1/guide`
- `/v1/parking`
- `/v1/flight-status`
- `/v1/baggage-check`
- `/v1/customs-rules`
- `/v1/self-service-options`
- `/v1/priority-lane-eligibility`
- `/v1/facilities`
- `/v1/shops`
- `/v1/readiness`

MCP 도구:
- `tool_get_coverage`
- `tool_get_guide`
- `tool_get_departure_readiness`
- `tool_get_parking_status`
- `tool_get_flight_status`
- `tool_check_baggage_rules`
- `tool_get_customs_rules`
- `tool_get_self_service_options`
- `tool_get_priority_lane_eligibility`
- `tool_find_facilities`
- `tool_find_shops`

## 신뢰 계약

모든 공개 응답에는 아래 메타 정보가 반드시 포함됩니다.
- `source`
- `freshness`
- `updated_at`
- `coverage_note`

동작 원칙은 다음과 같습니다.
- 지원하지 않는 공항이나 도메인은 숨기지 않고 명시합니다.
- `forecast` 데이터는 `live`처럼 보이게 만들지 않습니다.
- 지원 범위 안의 실시간 소스가 실패하면 추정값을 만들지 않고 bounded unavailable 상태를 반환합니다.
- ICN 주차 응답에는 요금 기준 설명이 들어갈 수 있지만, 숫자형 요금 추정은 임의로 만들지 않습니다.
- KAC 주차 응답에는 할인/예약 정책을 `policy_notes`로 따로 보여 줍니다.
- KAC readiness는 공식 processing/crowd 신호가 있는 공항에서만 해당 신호를 붙입니다.
- readiness의 `facility_hints`는 관련 `traveler_flags`가 있을 때만 노출합니다.
- 미래 날짜 readiness는 의도적으로 범위 밖입니다. 이 웨이브에서는 `flight-status`만 미래 날짜 ICN 항공편을 공식 지원합니다.

## 빠른 시작

```bash
cp .env.example .env
uv sync --extra dev
uv run departure-ready-api
```

API 문서:
- `http://127.0.0.1:8000/docs`
- 같은 프로세스에서 제공되는 원격 MCP: `http://127.0.0.1:8000/mcp`

STDIO MCP 실행:

```bash
uv run departure-ready-mcp
```

자주 쓰는 환경 변수:
- `DEPARTURE_READY_KAC_SERVICE_KEY`
- `DEPARTURE_READY_IIAC_SERVICE_KEY`
- `DEPARTURE_READY_HTTP_TIMEOUT_SEC`
- `DEPARTURE_READY_HTTP_PORT`
- `DEPARTURE_READY_PUBLIC_HTTP_URL`
- `DEPARTURE_READY_PUBLIC_MCP_URL`

실시간 서비스 키가 없어도 정책성 엔드포인트는 동작합니다. 대신 실시간 도메인은 공식 unavailable 상태를 명시적으로 반환합니다.

미래 날짜 ICN 항공편 예시:

```bash
curl "http://127.0.0.1:8000/v1/flight-status?airport_code=ICN&travel_date=2026-03-25"
```

`/v1/readiness`는 당일 기준만 지원하며 `travel_date`를 받지 않습니다.

KAC 접근성 시설 조회 예시:

```bash
curl "http://127.0.0.1:8000/v1/facilities?airport_code=GMP&category=wheelchair"
```

의도 기반 readiness 힌트 예시:

```bash
curl "http://127.0.0.1:8000/v1/readiness?airport_code=GMP&traveler_flags=wheelchair"
```

## Render 배포

Render direct 배포 정의는 [`render.yaml`](render.yaml)에 들어 있습니다.

권장 런타임 환경 변수:
- `DEPARTURE_READY_ENV=prod`
- `DEPARTURE_READY_PUBLIC_HTTP_URL=https://<your-service>.onrender.com`
- `DEPARTURE_READY_PUBLIC_MCP_URL=https://<your-service>.onrender.com/mcp`
- `DEPARTURE_READY_PUBLIC_MCP_URL`는 선택값입니다. 비워 두면 `DEPARTURE_READY_PUBLIC_HTTP_URL/mcp`로 계산합니다.
- `DEPARTURE_READY_KAC_SERVICE_KEY`
- `DEPARTURE_READY_IIAC_SERVICE_KEY`

Hosted canary workflow:
- [`.github/workflows/canary.yml`](.github/workflows/canary.yml)
- 로컬 keyed smoke와 hosted HTTP/MCP 검사를 함께 실행합니다.
- `DEPARTURE_READY_PUBLIC_HTTP_URL`, `DEPARTURE_READY_KAC_SERVICE_KEY`, `DEPARTURE_READY_IIAC_SERVICE_KEY` 중 하나라도 없으면 즉시 실패합니다.
- `DEPARTURE_READY_PUBLIC_MCP_URL`는 선택값이며, 없으면 `DEPARTURE_READY_PUBLIC_HTTP_URL/mcp`를 사용합니다.
- 결과 리포트는 GitHub Actions artifact로 남깁니다.

## 검증

```bash
uv run pytest
uv run ruff check .
uv run python -m departure_ready.smoke
```

공개 URL이 없는 상태에서 hosted canary를 dry-run으로 확인하려면 다음 명령을 사용합니다.

```bash
uv run python -m departure_ready.smoke --mode hosted
```

대표 릴리스 질의는 [`tests/test_qa_corpus.py`](tests/test_qa_corpus.py)에 들어 있습니다. Wave 3 이후 launch/smoke 회귀는 [`tests/test_launch_wave2.py`](tests/test_launch_wave2.py), [`tests/test_remote_launch_wave3.py`](tests/test_remote_launch_wave3.py), [`tests/test_future_flight_surface_wave3.py`](tests/test_future_flight_surface_wave3.py), [`tests/test_launch_wave5.py`](tests/test_launch_wave5.py), [`tests/test_remote_mcp_wave5.py`](tests/test_remote_mcp_wave5.py)에서 확인할 수 있습니다.

## 문서 읽는 순서

아래 순서대로 보면 프로젝트 맥락을 빠르게 파악할 수 있습니다.
1. [`docs/PRD.md`](docs/PRD.md)
2. [`docs/EXEC_PLAN.md`](docs/EXEC_PLAN.md)
3. [`docs/SOURCE_REGISTRY.md`](docs/SOURCE_REGISTRY.md)
4. [`docs/CODEX_PROMPTS.md`](docs/CODEX_PROMPTS.md)
