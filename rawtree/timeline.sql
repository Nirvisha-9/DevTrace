-- How working state evolves per cycle while evidence keeps growing.
-- RawTree columns are schema-free (Dynamic), so values are cast explicitly.
-- Run: .venv/bin/python scripts/rawtree_timeline.py "stripe-python"
SELECT toInt64OrZero(toString(cycle)) AS cyc,
       min(toString(timestamp)) AS started_at,
       anyIf(toString(question), toString(event_type) = 'question_selected') AS question,
       max(toInt64OrZero(toString(evidence_count))) AS evidence_count,
       max(toInt64OrZero(toString(new_evidence_count))) AS new_evidence_count,
       max(toInt64OrZero(toString(working_state_size))) AS working_state_size,
       max(toInt64OrZero(toString(archived_count))) AS archived_count,
       max(toInt64OrZero(toString(stale_claim_count))) AS stale_claim_count,
       max(toInt64OrZero(toString(impacted_file_count))) AS impacted_file_count,
       sum(toInt64OrZero(toString(input_tokens))) AS input_tokens,
       sum(toInt64OrZero(toString(output_tokens))) AS output_tokens
FROM {table}
WHERE toString(topic) = {topic}
GROUP BY cyc
ORDER BY cyc
