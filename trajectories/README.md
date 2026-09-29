# Trajectories

Real model rollouts are ignored by git. After grading, append one JSON object
per episode to `episode_scores.jsonl` using the fields enforced by
`uc_bench.evaluation.EpisodeScoreRow`: run/model IDs, condition, scenario,
seed, 0–100 headline and component scores, contract validity, infrastructure
failure, and decision correctness.

Never put provider credentials, sealed sample IDs, per-patient outcomes, or
individual validation predictions in a trajectory file.

Episode trajectories will be written as JSONL and are ignored by Git by default.
Each record will pin task, condition, variant, seed, provider/model version,
events, artifact hashes, token usage, cost, final decision, reward components,
and failure labels.
