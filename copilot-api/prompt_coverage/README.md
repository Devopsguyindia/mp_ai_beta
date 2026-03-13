# Prompt Coverage Assets (V1)

This folder generates and stores production-style prompt coverage assets for:

- `sales` copilot
- `inventory` copilot

## Generated outputs

- `intent_catalog.json`
- `prompt_templates.csv`
- `prompt_to_sql_contracts.json`
- `prompt_dataset_v1.jsonl` (target: 300 prompts)
- `generation_summary.json`

## How to generate

Run:

```bash
python "copilot-api/prompt_coverage/generate_prompt_assets.py"
```

## Dataset format (`prompt_dataset_v1.jsonl`)

Each line is a JSON object with:

- `prompt_id`
- `copilot`
- `intent_id`
- `question`
- `priority`
- `expected_contract_id`
- `required_filters`
- `safety`
- `tags`

## Safety assumptions

- SELECT-only
- mandatory `idcompany` scoping

