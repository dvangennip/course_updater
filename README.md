# course\_updater
A script library to automate updating MS Teams based on Moodle input

## Requirements
- Python 3.7+
- Python modules: splinter, keyring
- Mozilla Firefox + Geckodriver (on macOS, easiest install via `brew install geckodriver`)
	- Alternatively, Chrome could be used with some updates to the code
- Powershell 7+ (Core is sufficient) (on macOS, use `brew install --cask powershell`)
- Powershell MicrosoftTeams module (preview version has private channel cmdlets, latest public release version may not)
- Tested only on MacOS 10.15 Catalina
	- Likely to work on any POSIX system
	- Use on Windows may need some changes to filepaths, etc.

## Guide
- course\_updater.py is best used as a library called from another script file
- Rather than editing course\_updater.py, import its classes into your own script
- Look at the update\_example.py file for an idea

## Example script
````python
from course_updater import MoodleUpdater, TeamsUpdater

my_user_file = "empty for now, will become a reference to a file"

with MoodleUpdater(course_id, username, password) as mu:
	# let's download a list of students currently enrolled
	my_user_file = mu.get_users_csv()

with TeamsUpdater(my_user_file, username, password) as tu:
	# start by importing the freshly downloaded list
	tu.import_user_list()

	# create a new team and add some channels
	team_id = tu.create_team('Robotics project')
	
	tu.create_channel(team_id, 'QnA forum')

	for x in range(1,9):
		tu.create_channel(team_id, f'Class {x}', channel_type='private')

	# add some staff as owners to the team
	tu.add_users_to_team(team_id, tu.user_stafflist, role='Owner')

	# find a subset of users based on search criteria, like group membership
	students = tu.find_users('group', 'Project - Robotics')
	
	# sync team membership for students
	#   the script will compare with who's already a member
	#   and only add/remove people when needed
	tu.update_team(team_id, students, role='Member')
````

## Known issues
- headless state of Firefox/geckodriver crashes (on macOS, as of Sept 2021)
- Teams module currently returns nice.name@domain or zID@domain for users, randomly it seems, making identification harder as it requires a lookup against known emails to get zIDs.

## TO DO
- Mask password in plain text terminal output on ConnectTeams login step
- Perform some of the parsing into useful variables in TU.export_student_list already in TU.import. This will make those variables available for filtering/searching. Example variables:
	- project
	- team
	- lab/tech stream?
	- demonstrators, etc, could be parsed as well
- Make find_users more generic
	- ability to search for any variable by its name (as User class vars may increase in the future)
	- exact=true as method parameter rather than separate search type
	- look into custom filter function for python object lists/dicts
	- alternatively, because sql queries are powerful, it may be efficient to build a db on import
- Publish as private repo on github
	- Transfer these to do's to issues?
- Add automatic ability to recognise Connect-MicrosoftTeams login account (zID) and add this to exclusion IDs to avoid accidental self-removal?
	- alt idea: if this is actually desired, have a prompt to check and get approval -> add a current_user variable to check against
- Error handling
	- errors should go into the log
	- data output is unpredictable with ConvertToJson enabled but can cause crashes, so need to catch this properly
- Integrate user_stafflist into default users list
	- Requires easy way to filter out staff
- Allow searching by class id AND group(ing) data.
	- a filter function might ideally take 2+ search terms
	- current `find\_users` method could be chained to achieve multiple search terms in `x AND y` fashion, not `OR` or `ANY`.
- Login procedure for some of the classes is the same so standardise, or make a base class for them
	- MoodleBrowser may be a suitable candidate?
- Split TeamsUpdater class into two separate classes:
	- One just a wrapper for the MSTeams powershell module
	- Another for importing/exporting/managing student/staff lists -> easier to adopt elsewhere
- Do not require input path for TeamsUpdater class (work that into the import function)
- Split out into separate files, making it more like a library?
- Export groups and groupings into students csv
	- Extract mentor/demo from grouping data for ENGG1000?
