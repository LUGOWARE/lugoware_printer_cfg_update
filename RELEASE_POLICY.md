# Release policy

- `lugoware_config` display versions come from the `FLEX4_<model>_V...` header in `printer_base.cfg` at the corresponding Git revision. Do not assign a system version to config.
- `lugoware_system` has an independent version, starting at `1.2.1`. Increment its patch version once per future published system update (1.2.2, 1.2.3, ...), unless the owner specifies another version. Installing or reinstalling does not increment it.
- Replace release notes with only the changes in that release; do not append older release content. Use concise customer-facing Korean, English and Simplified Chinese.
- Keep equivalent system releases aligned across GitHub M5P/M8P and Gitee M5P. Preserve repository-specific exclusions.
- Config-only publishing must preserve the existing system version and notes.
