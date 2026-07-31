# ZeroOps cost-optimization policy

Cost optimization is a required decision dimension, never an afterthought.
Recommendations must preserve explicit security, reliability, compliance, data
residency, recovery, and performance requirements.

## Evidence rules

- Never invent a price, saving amount, percentage, billing meter, discount, or
  forecast.
- Numerical amounts are permitted only when the request includes a verified
  pricing snapshot with currency, source, and capture time.
- Label uncertainty and identify the exact utilization, retention, traffic,
  storage, egress, concurrency, or SLO measurement needed.
- Separate architecture recommendations from verified billing calculations.

## Preferred optimization order

1. Remove unused work and duplicate model/deployment calls.
2. Use deterministic scanning, caching, request hashing, batching, and bounded
   context before increasing model size or token limits.
3. Prefer serverless or scale-to-zero execution for intermittent workloads.
4. Right-size from measured utilization; configure autoscaling bounds and idle
   behavior.
5. Apply Blob lifecycle tiers and retention appropriate to artifact value.
6. Minimize data movement, public egress, duplicate logs, and unbounded
   telemetry retention.
7. Use the least expensive service tier that satisfies the approved SLO and
   security boundary.
8. Consider reservations or savings commitments only after stable, measured
   baseline utilization proves they are appropriate.

## Required recommendation shape

Every cost recommendation identifies:

- the approved component it affects;
- evidence or the missing measurement;
- the mechanism;
- qualitative impact (`low`, `medium`, `high`, or `unknown`);
- security, reliability, and operational tradeoffs;
- whether verified pricing is required before approval.

AI token usage is also a cost. Repository analysis runs only for a new commit
or prompt/model version. Terraform generation runs only for a new approved
plan digest. Output is capped, and schema repair is attempted at most once.

