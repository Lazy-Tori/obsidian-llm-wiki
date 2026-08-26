# Log

시간순 기록. 형식 고정: `## [YYYY-MM-DD] operation | 제목`
`grep "^## \[" log.md | tail -5` 로 최근 이력을 뽑을 수 있어야 한다.

operation: `setup` | `ingest` | `query` | `lint` | `daily` | `emerge` | `promote` | `schema`

여기부터 아래로 쌓인다. 첫 줄은 볼트를 세운 날의 `setup` 기록으로 시작하면 된다.
