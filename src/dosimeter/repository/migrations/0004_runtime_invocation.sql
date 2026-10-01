-- Which AgentCore Runtime ran the turn, when it ran there instead of in the CLI.

ALTER TABLE run_records ADD COLUMN runtime_arn text;
ALTER TABLE run_records ADD COLUMN runtime_session_id text;
