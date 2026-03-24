# Launch checklist

## Product
- [ ] README matches actual implementation
- [ ] supported airports clearly stated
- [ ] unsupported features clearly stated
- [ ] response examples include freshness and source

## Source operations
- [ ] KAC keys configured
- [ ] IIAC keys configured
- [ ] canary requests defined for each live source
- [ ] timeout and retry settings reviewed
- [ ] schema drift watchlist documented

## API
- [ ] `/healthz` healthy
- [ ] `/docs` renders
- [ ] envelope contract stable
- [ ] error responses consistent

## MCP
- [ ] stdio server boots
- [ ] no stdout logging corruption
- [ ] basic tool smoke passes
- [ ] guide/coverage tools return current docs

## QA
- [ ] unit tests pass
- [ ] connector smoke passes
- [ ] readiness happy-path corpus reviewed
- [ ] baggage/customs edge cases reviewed

## Safety / trust
- [ ] no guessed live values
- [ ] every readiness answer includes coverage note
- [ ] customs guidance not presented as legal advice
- [ ] baggage guidance not presented as airline guarantee
