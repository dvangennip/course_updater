# teams\_updater
A script to automate updating MS Teams based on Moodle input

## Requirements
- Python 3.7+
- Python modules: splinter, keyring
- Mozilla Firefox + Geckodriver (easiest install via `brew install geckodriver`)
	- Alternatively, Chrome could be used with some updates to the code
- Powershell 7+ (Core is sufficient)
- Powershell MicrosoftTeams module (preview version has private channel cmdlets, latest public release version may not)
- Tested only on MacOS 10.15 Catalina
	- Likely to work on any POSIX system
	- Use on Windows may need some changes to filepaths, etc.

## TO DO
- Work around current add-user as owner bug
- Add automatic ability to recognise Connect-MicrosoftTeams login account (zID) and add this to exclusion IDs to avoid accidental self-removal?
	- alt idea: if this is actually desired, have a prompt to check and get approval -> add a current_user variable to check against
- Error handling
	- errors should go into the log
	- data output is unpredictable with ConvertToJson enabled but can cause crashes, so need to catch this properly
- Integrate user_whitelist into default users list
	- Requires easy way to filter out staff
- Allow searching by class id and group(ing) data.
	- a filter function might ideally take 2+ search terms
	- current `find\_users` method could be chained to achieve multiple search terms in `x AND y` fashion, not `OR` or `ANY`.
- Do not require input path for teams\_updater class (work that into the import function)
- Split out into separate files, making it more like a library?
- Login procedure for some of the classes is the same so standardise, or make a base class for them
	- MoodleBrowser may be a suitable candidate?

## BUGS
- headless state of Firefox/geckodriver crashes.
- Teams module currently returns nice.name@domain or zID@domain, randomly it seems.
- Teams module currently does not allow for users to be added or removed as owners of a private channel.