# Perf snapshot

## Endpoint latency (20 hits, sequential)

| Endpoint | p50 ms | p95 ms | min ms | max ms |
|---|---|---|---|---|
| `/api/agg/articles?limit=20&hours=48` | 245.5 | 330.0 | 44.0 | 613.1 |
| `/api/agg/publishers-latest?hours=168` | 71.0 | 96.0 | 46.0 | 120.6 |
| `/api/essays?limit=10` | 407.8 | 1070.9 | 164.0 | 1138.4 |
| `/api/agg/trending?hours=24&limit=6` | 121.0 | 195.0 | 96.0 | 315.0 |
| `/api/agg/network-stats` | 44.5 | 151.0 | 43.9 | 161.0 |

## Full RSS ingest

- wall_clock_s: 35.81
- publishers_ran: 48
