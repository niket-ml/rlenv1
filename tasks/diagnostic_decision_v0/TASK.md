# Biomarker evidence decision packet

You are reviewing a completed biomarker-validation evidence packet. This is a
short diagnostic task: do not build or refit a predictor. Inspect `packet.json`
and the decision policy below, write `submission/final_submission.json` using
`schemas/final_submission.schema.json`, then call `submit_packet` exactly once.

## Prespecified research decision policy

Choose `advance` only when all of these are true:

- validation AUC is at least 0.70;
- the AUC interval lower bound is strictly greater than 0.50;
- permutation p-value is at most 0.05;
- evaluated sample count is at least 100; and
- the validation result is usable under the prespecified feature contract; and
- there is no hard integrity failure.

Choose `stop` when a hard unresolved integrity failure makes the result
uninterpretable. Otherwise choose `insufficient_evidence`.

Diagnose only failures supported by the packet. Use exact controlled vocabulary
from the schema. Cite evidence using IDs present in `packet.json`; unsupported or
invented IDs are rejected, while citing additional valid packet evidence does
not reduce the score. Select the smallest next action that resolves the
dominant failure. A correct decision with generic caution is not a complete
answer, and abstention is penalized in sufficient-evidence packets.

The public per-packet score is 40% decision, 30% diagnostic-code F1, 20% next
action, and 10% recall of required evidence. Confidence is retained for
calibration across packets and is not scored against a hidden per-item target.

This is a research advancement decision, not permission for clinical use.
