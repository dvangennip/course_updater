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
- Add automatic ability to recognise Connect-MicrosoftTeams login account (zID) and add this to exclusion IDs to avoid accidental self-removal?
	- alt idea: if this is actually desired, have a prompt to check and get approval -> add a current_user variable to check against
- Error handling
	- errors should go into the log
	- add_user for example doesn't catch all errors, assumes things are fine besides known errors
	- data output is unpredictable with ConvertToJson enabled but can cause crashes, so need to catch this properly
- (optional) add remove_allowed flags to update_* methods so it can be used to add people if necessary, but not remove any
	- (this allows other owners to add people when desired without that going through the script)
- Refactor update scripts so multiple courses in one term can go into one script, reusing logins to speed up process
	- may require separating logins from doing actual operations, e.g., in MoodleUpdater
- Integrate user_whitelist into default users list
	- Requires easy way to filter out staff
- Allow searching by class id and group(ing) data.
	- a filter function might ideally take 2+ search terms
	- current `find\_users` method could be chained to achieve multiple search terms in `x AND y` fashion, not `OR` or `ANY`.
- Do not require input path for teams\_updater class (work that into the import function)
- Make log function available outside of teams\_updater class (for example for use in the Moodle class)
- Change name to lms_updater and maybe split out into separate files, making it more like a library?
- Login procedure for some of the classes is the same so standardise, or make a base class for them