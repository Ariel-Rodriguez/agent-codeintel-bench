Persistent-understanding task, stage 2 (new session).

In a NEW session in the same repository, answer from prior work: which module
defines `GuardedTransaction`, which module publishes the durable operation
journal, and which module resolves a secret value only inside the supervisor?
Name the files. State explicitly if you are re-exploring rather than reusing
prior knowledge.

Stage 2b (staleness): between stage 1 and stage 2, apply a source change (for
example `benchmarks/repair/bug.patch`) and check whether the enhanced arm
notices that its on-disk index is stale instead of trusting it.
