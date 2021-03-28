# teams\_updater
A script to automate updating MS Teams based on Moodle input

## Requirements
- Python 3.7+
- Python modules: splinter, keyring
- Mozilla Firefox + Geckodriver (easiest install via brew)
	- Alternatively, Chrome could be used with some updates to the code
- Powershell 7+ (Core is sufficient)
- Powershell MicrosoftTeams module (v1.1.9-preview has private channel cmdlets, latest public release version may not)
- Tested only on MacOS 10.15 Catalina
	- Likely to work on any POSIX system
	- Use on Windows may need some changes to filepaths, etc.

## TO DO
- Move away from parsing command line output, use ConvertTo-Json instead to make data exchange reliable
- Complete update team method and related methods
- Standardise the use of dicts and/or lists as input to methods
- Simplify methods to not work on core data, but rather work with input and output (more flexible that way)
- Do not require input path for class (work that into the import function)
- Error handling
- Allow searching by class id and group(ing) data.
	- It may make using per-class lists obsolete.
	- ClassItems would be become descriptions of a users list search term(s) and corresponding team or channelname (+ team id).
	- a filter function might ideally take 2+ search terms
- Feature: create teams based on grouping data (+ add members as owners)
- Add extra data to student User
	- Moodle groupings
		- Project, Team, Tech stream are particularly interesting to pick out
		- the above would allow linking to demonstrators and coordinators based on a reference list
