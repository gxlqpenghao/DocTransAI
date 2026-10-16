# OfficeCLI isolated evaluation

These scripts are experimental, not imported by DocTransAI production code. Use a disposable output directory and an explicitly downloaded, checksum-verified OfficeCLI binary. The first evaluation used v1.0.157 on macOS ARM64.

```bash
python experiments/officecli_fixture.py outputs/officecli-evaluation
# Write data.json in that directory with project, date, deadline, result values.
python experiments/officecli_probe.py --binary /absolute/path/to/officecli --root outputs/officecli-evaluation
python experiments/officecli_checks.py --binary /absolute/path/to/officecli --root outputs/officecli-evaluation
```

The fixture uses python-docx, openpyxl and Pillow. Create data.json with synthetic values only, for example `{"project":"合成测试项目","date":"2026-10-16","deadline":"2026-10-17 20:00","result":"设备运行正常"}`. Reuse a fresh directory on each run: merge deliberately does not overwrite previous outputs.

The probe optionally reads `business-template.docx` and `business-template.xlsx` if manually supplied as local copies. Do not commit these files or output logs/images. It records command timing, output and exit status; exit zero alone is not a quality pass. Inspect unresolved placeholders and warnings, then independently open/render the saved files. HTML/screenshots may require a browser and need comparison with the production renderer, including all pages/columns.

The checks intentionally include a placeholder split across Word runs, header text, merged spreadsheet cells, a formula cache read and a failing atomic batch. Keep results separate from LLM semantic quality: these scripts do not call a model or DataProxy.

Use explicit save/close or `OFFICECLI_RESIDENT_FLUSH=each` before external tools read modified files. Do not enable automatic installation or updates in production; pin the binary. No OfficeCLI runtime dependency is added by this experiment.
