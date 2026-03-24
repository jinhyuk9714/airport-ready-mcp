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
- [x] hosted canary workflow committed
- [x] scheduled canary fails fast on missing required ops config
- [x] timeout and retry settings reviewed
- [x] schema drift watchlist documented

## API
- [x] `/healthz` healthy
- [x] `/docs` renders
- [x] remote MCP mount responds on `/mcp`
- [x] envelope contract stable
- [x] error responses consistent

## MCP
- [x] stdio server boots
- [x] no stdout logging corruption
- [x] basic tool smoke passes
- [x] guide/coverage tools return current docs
- [x] streamable-http mount shares the same trust contract

## QA
- [x] unit tests pass
- [x] connector smoke passes
- [x] readiness happy-path corpus reviewed
- [x] baggage/customs edge cases reviewed
- [x] hosted canary dry-run stays bounded without public URLs

## Deployment
- [x] Render blueprint committed
- [x] public MCP URL falls back to `public_http_url + "/mcp"`
- [x] CI validates smoke + hosted canary dry-run
- [x] hosted canary treats `public_mcp_url` as optional

## Safety / trust
- [x] no guessed live values
- [x] every readiness answer includes coverage note
- [x] customs guidance not presented as legal advice
- [x] baggage guidance not presented as airline guarantee
