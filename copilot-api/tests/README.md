## Tests (ephemeral scripts)

V1 requirement: dynamic test scripts should be created in a dedicated folder and deleted after use.

Implementation approach:

- At runtime, create a unique directory under `/tmp/copilot-tests/<uuid>/`
- Write any generated script files into that directory
- Execute them
- Always delete the directory in a `finally` block

In local Windows development, the service will use the system temp folder equivalent.

## Prompt regression runner

Run the generated prompt set against a running API:

```bash
python "copilot-api/tests/prompt_regression_runner.py" --idcompany 212
```

Optional quick run:

```bash
python "copilot-api/tests/prompt_regression_runner.py" --idcompany 212 --max-prompts 50
```

Outputs:

- `copilot-api/tests/output/regression-summary-<timestamp>.json`
- `copilot-api/tests/output/regression-failures-<timestamp>.csv`

