# LUGOWARE screen translations

Each UTF-8 JSON catalog maps English UI message IDs to a locale translation.
The 32 locale filenames match KlipperScreen's locale IDs, including `jp`, `rs`,
`pt_BR`, `zh_CN` and `zh_TW`. `en.json` is the source message list.

Custom panels call `_()` at runtime. `maintenance/lugo_i18n.py` wraps the selected
official gettext translation and uses these catalogs when upstream has no
translation. Language switching reinstalls that wrapper and reloads the panels.
Menu titles use Jinja `{{ _('Prepare') }}` expressions. Preheat labels and known
heater-test prompt labels are translated without changing their command IDs.

To add or correct a message, update all catalogs with the same key. Preserve
format fields such as `{v0}`, `{pin}`, `{value}` and intentional line breaks.
Never translate material profile names, filenames, pins or G-code commands.
Run `python3 -m unittest discover -s tests -p test_i18n.py` before publishing.
These initial custom translations have not been reviewed by native speakers of
every language. Existing official translations remain upstream's responsibility;
missing official messages and arbitrary third-party diagnostics fall back to
their source text.

Run the main installer to distribute catalog changes. Model-branch post-merge
hooks only merge configuration and preserve the saved screen language; they do
not download new panels or catalogs. No online translation service is required.
