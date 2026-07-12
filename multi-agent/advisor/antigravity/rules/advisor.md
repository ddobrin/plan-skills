# Rule: Execute yourself, escalate judgment

- The main agent implements; it does not delegate routine work.
- Escalate to a read-only advisor child agent only for: design forks
  with multiple viable options, problems that survived 2 fix attempts,
  changes touching >5 files or a public API, or security-sensitive
  decisions.
- Advisor prompts must be self-contained: problem, options, file paths,
  constraints. No raw logs.
- Advisor responses must be: one recommendation, why, risks, what to
  avoid. The main agent follows the recommendation.
