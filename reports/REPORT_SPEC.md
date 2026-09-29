# UC-Bench leaderboard and failure-atlas specification

The report leads with the benchmark state, not a model ranking. It must always
distinguish:

- authentic GSE92415 evidence;
- synthetic and planted controlled states;
- deterministic fixture results;
- actual model trajectories.

The leaderboard remains empty until at least two models have repeated valid
trajectories. Each row names the complete model, agent harness, runtime, task
version, condition, number of trajectories, graceful-failure mean and clustered
interval, and contract-valid rate. It never presents a base-model name as if
the harness and container were irrelevant.

The failure atlas reports stable diagnostic codes, their rates and confidence
intervals, a decision-confusion table, expected-versus-realized AUC calibration,
data-withheld retention, and breaking-point curves. Every example links to a
replayable event record and artifact digest. Narrative examples illustrate a
metric; they do not create the metric.

Run `make report` to produce a self-contained local HTML report. Before real
model runs it deliberately displays “PRE-RESULT — NO MODEL RANKING” and shows
only environment validation controls. Those controls include independently
recomputed model/data claims and a structured false-pass attempt; the report
must not describe agent-authored audit fields as executed evidence merely
because they are schema-valid.
