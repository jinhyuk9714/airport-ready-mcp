# QA corpus

Representative release queries that should keep passing:

1. "김포공항인데 지금 차 끌고 가도 돼?"
Expected:
- `/v1/readiness?airport_code=GMP&going_by_car=true`
- response stays bounded even without live keys
- parking unavailable is explicit, not guessed

2. "김치 120ml 같은데 국제선 기내반입 돼?"
Expected:
- `/v1/baggage-check?trip_type=international&item_query=kimchi&liquid_ml=120`
- `carry_on_allowed=false`
- explanation mentions liquid-like screening treatment

3. "면세 포함 900달러에 담배 250개비면 신고해야 해?"
Expected:
- `/v1/customs-rules?purchase_value_usd=900&cigarette_count=250`
- `declaration_required=true`
- warnings mention the 200-stick allowance

4. "김포공항에서도 임산부 우대출구 쓸 수 있어?"
Expected:
- `/v1/priority-lane-eligibility?airport_code=GMP&user_profile=pregnant traveler`
- product answers that this repo only supports the Incheon priority-lane policy
- no ICN-only policy is silently generalized to KAC airports

5. "인천 주차장 지금 비었어?"
Expected:
- `/v1/parking?airport_code=ICN`
- with no live key or live outage, return `ok=true` with empty lots and explicit unavailable note
- never fabricate parking counts

The automated version of this corpus lives in `tests/test_qa_corpus.py`.
