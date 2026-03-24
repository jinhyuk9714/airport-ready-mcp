# Launch checklist

## Product
- [x] README matches actual implementation
- [x] supported airports clearly stated
- [x] unsupported features clearly stated
- [x] response examples include freshness and source

## Source operations
- [ ] KAC keys configured
- [ ] IIAC keys configured
- [x] canary requests defined for each live source
- [x] timeout and retry settings reviewed
- [x] schema drift watchlist documented

## API
- [x] `/healthz` healthy
- [ ] `/docs` renders
- [x] envelope contract stable
- [x] error responses consistent

## MCP
- [x] stdio server boots
- [x] no stdout logging corruption
- [x] basic tool smoke passes
- [x] guide/coverage tools return current docs

## QA
- [x] unit tests pass
- [x] connector smoke passes
- [x] readiness happy-path corpus reviewed
- [x] baggage/customs edge cases reviewed

## Safety / trust
- [x] no guessed live values
- [x] every readiness answer includes coverage note
- [x] customs guidance not presented as legal advice
- [x] baggage guidance not presented as airline guarantee
