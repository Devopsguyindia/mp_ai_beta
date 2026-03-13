## Tests (ephemeral scripts)

V1 requirement: dynamic test scripts should be created in a dedicated folder and deleted after use.

Implementation approach:

- At runtime, create a unique directory under `/tmp/copilot-tests/<uuid>/`
- Write any generated script files into that directory
- Execute them
- Always delete the directory in a `finally` block

In local Windows development, the service will use the system temp folder equivalent.

