# Batch Submission Requirements

## Batch semantics

- `submit_batch` must be atomic.
- If any order in the batch is invalid, the function must return a failure result for the batch.
- When a batch fails, the implementation must not persist any orders from that request.
- Partial success is not allowed for this endpoint.
