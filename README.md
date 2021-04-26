# teams\_updater
A script to automate updating MS Teams based on Moodle input

## Requirements
- Python 3.7+
- Python modules: splinter, keyring
- Mozilla Firefox + Geckodriver (easiest install via `brew install geckodriver`)
	- Alternatively, Chrome could be used with some updates to the code
- Powershell 7+ (Core is sufficient)
- Powershell MicrosoftTeams module (v1.1.9-preview has private channel cmdlets, latest public release version may not)
- Tested only on MacOS 10.15 Catalina
	- Likely to work on any POSIX system
	- Use on Windows may need some changes to filepaths, etc.

## TO DO
- Error handling
	- data output is unpredictable with ConvertToJson enabled but can cause crashes, so need to catch this properly
- Integrate user_whitelist into default users list
	- Requires easy way to filter out staff
- Standardise the use of dicts and/or lists as input to methods
- Add extra data to student User
	- Moodle groupings
- Allow searching by class id and group(ing) data.
	- a filter function might ideally take 2+ search terms
	- current `find\_users` method could be chained to achieve multiple search terms in `x AND y` fashion, not `OR` or `ANY`.
- Modify `update_channel` to allow syncing owners only (i.e., role based filtering and adding)
- Do not require input path for class (work that into the import function)
- Make log function available outside of teams_updater class (for example to the Moodle part)
- Make teamsupdater connect 'lazy loading' to simplify custom scripts, maybe through a lazy_connect method so we keep the option to directly get going
- Change name to lms_updater and maybe split out into separate files, making it more a library?
