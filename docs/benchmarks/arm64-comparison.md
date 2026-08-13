## ReliefRelay arm64 optimization benchmark

Quality guard: **PASS**

| Metric | Full precision | Q5_1 | Change |
| --- | ---: | ---: | ---: |
| Model size | 74.10 MiB | 30.68 MiB | 58.60% smaller |
| Median inference | 0.273 s | 0.273 s | 0.00% reduction |
| P95 inference | 0.307 s | 0.302 s | 1.63% reduction |
| Median real-time factor | 0.0316 | 0.0320 | 1.27% increase |
| Mean word error rate | 11.23% | 8.79% | -2.44 pp |
| Structured-field accuracy | 97.78% | 100.00% | +2.22 pp |

Measured on Apple M4 (`arm64`, Darwin) with 6 threads, 9 fixtures and 63 measured inferences.
The Q5_1 file was generated on the runner from the verified full-precision model.
