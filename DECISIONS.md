# DECISIONS.md — NexusAPI Design Decisions

## Question 1: Why does the credit system use a transaction ledger instead of a balance column?

The credit system records every movement of credits as an immutable row in the CreditTransactions table rather than maintaining a mutable balance column on the organisations table. This decision stems from the fundamental difference between a log and a register. A balance column is a single mutable value that can be overwritten, and once overwritten, the previous state is lost. A ledger, by contrast, preserves the complete history of every addition and deduction, making it possible to audit any balance at any point in time by summing the rows up to that moment.

In a production credit or payment system, auditability is not optional. If a customer disputes a charge, or if a bug causes an incorrect deduction, the team needs to trace exactly what happened and when. With a balance column, that information is gone the moment the next write occurs. With a ledger, every transaction is permanent and the current balance is always derivable as the sum of all amounts for that organisation.

The tradeoff is performance: computing a balance from a sum of rows is slower than reading a single column. For organisations with thousands of transactions, this query could become expensive. The mitigation is straightforward: add an index on (organisation_id, created_at) to make the aggregation efficient, and if scale demands it, introduce a materialised balance cache that is updated atomically alongside the ledger insert — never instead of it. The ledger remains the source of truth; any cached balance is a derived optimisation.

## Question 2: How did you handle the simultaneous credit deduction problem?

The core of the solution is SELECT ... FOR UPDATE at the database level. When deduct_credits is called, it begins a database transaction and immediately acquires a row-level lock on all CreditTransactions rows for the target organisation using a SELECT with FOR UPDATE. This means that if two requests arrive simultaneously, the second one will block at the database level until the first transaction either commits or rolls back.

Here is the exact sequence: Request A enters deduct_credits, begins a transaction, and executes SELECT SUM(amount) FROM credit_transactions WHERE organisation_id = X FOR UPDATE. This locks all matching rows. Request A reads a balance of 25, confirms it is sufficient, inserts a deduction of -25, and commits. Now Request B, which was blocked at the SELECT step, acquires the lock, computes the sum again — which is now 0 — and raises InsufficientCreditsError. Only one request succeeds. There is no window in which both requests can read the same stale balance, because the FOR UPDATE lock serialises the reads.

I chose this over optimistic concurrency control with version numbers because the credit system requires strict consistency. An optimistic approach would allow both requests to read the same balance, attempt to write, and then one would fail on a version check. While valid, it requires retry logic at the application layer and adds complexity. The pessimistic locking approach is simpler, correct by construction, and appropriate for a system where credit contention is expected to be low relative to total request volume.

## Question 3: What happens when the background worker fails after credits have been deducted?

When a summarise job is enqueued, credits are deducted immediately and atomically before the job enters the background queue. If the ARQ worker subsequently fails — whether due to a crash, timeout, or exception during processing — the worker's exception handler catches the failure, marks the job as "failed" in the database, and issues a refund by inserting a positive credit transaction into the ledger.

This is a deliberate refund-on-failure strategy. The alternative would be to defer the deduction until the job completes successfully, but that introduces a different problem: a user could enqueue unlimited jobs without paying, effectively getting free API calls until the jobs complete. By deducting upfront and refunding on failure, the system maintains the invariant that credits are always reserved before work begins, while ensuring users are not permanently charged for work that was never delivered.

There is an edge case where the worker crashes so hard that the exception handler itself does not run. To address this, a periodic cleanup process could scan for jobs that have been in "pending" or "running" status for longer than the job timeout (five minutes) and refund their credits. This is not implemented in the current version but would be a straightforward addition via a scheduled ARQ task.

## Question 4: How does your idempotency implementation work, and where does it live?

The idempotency mechanism operates at two layers: the application layer performs a lookup, and the database layer enforces the constraint. When a request arrives with an Idempotency-Key header, the endpoint first queries the CreditTransactions table for an existing row with that key and the same organisation ID. If found, it returns the cached response without deducting credits again.

If no existing transaction is found, the request proceeds to deduct_credits, which inserts a new CreditTransaction row with the idempotency_key field set. The credit_transactions table has a unique partial index on idempotency_key (where idempotency_key IS NOT NULL). This means that even if two identical requests arrive simultaneously and both pass the application-level check (because neither has committed yet), only one INSERT will succeed. The second will violate the unique constraint, raise an IntegrityError, which is caught and translated into an IdempotencyConflictError. The handler then falls back to returning the original response.

This two-layer approach is essential because application-level checks alone are vulnerable to race conditions. Between the moment the application reads "no existing key" and the moment it inserts the new row, another request can do the same. The database unique constraint is the actual enforcement mechanism; the application check is an optimisation that avoids the overhead of hitting the constraint in the common case of non-concurrent duplicates.

## Question 5: What would break first at 10x the current load, and what would you do about it?

At ten times the current load, the most likely bottleneck is the credit balance computation. Every call to deduct_credits computes the balance by summing all CreditTransactions rows for the organisation while holding a FOR UPDATE lock. As transaction volume grows, this sum becomes more expensive, and the lock hold time increases, which serialises all credit operations for that organisation. Under heavy load, this creates contention that would degrade latency for all product endpoints.

The fix is to introduce a materialised balance column on the organisations table, updated atomically within the same transaction as the ledger insert. The ledger remains the source of truth for auditability, but the balance check reads from the cached column instead of computing a sum. The deduction transaction would then be: lock the organisation row (a single row lock instead of locking all transaction rows), check the cached balance, insert the ledger row, and decrement the cached balance — all within one transaction. This reduces the lock scope from all transaction rows to a single organisation row and eliminates the SUM aggregation entirely. The second bottleneck would be Redis for rate limiting under high concurrency, which could be addressed by switching to a Redis Cluster or by implementing local in-memory rate limiting with periodic synchronisation.
