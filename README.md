# course\_updater
A python library to automate updating MS Teams based on Moodle input

## Requirements
- Python 3.7+
- Python modules: `splinter`, `keyring`, `colorama` (can be installed with `pip`)
- Mozilla Firefox + Geckodriver (on macOS, easiest install via `brew install geckodriver`)
	- Alternatively, Chrome could be used with some updates to the code
- Powershell 7+ (Core is sufficient) (on macOS, use `brew install --cask powershell`)
- Powershell MicrosoftTeams module (preview version has private channel cmdlets, latest public release version may not)
- Tested only on macOS 10.15 and later
	- Likely to work on any POSIX system
	- Use on Windows may need some changes to filepaths, etc.

## Guide
- course\_updater.py is best used as a library called from another script file
- Rather than editing course\_updater.py, import its classes into your own script
- Look at the example files for an idea

## Example script
A simple demo example is shared below but look in the examples folder for more complete code you can adapt.

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

## Conventions for Moodle groups setup
While there is some room for configuration, a few ways to extract data from Moodle groups info is hardcoded. This means a Moodle site needs to follow these conventions to ensure this script works:

- Projects must be named `Project Group - NAME` (where name is the project name)
- Project teams must have `team` as part of their name, so `XYZ Team B` works but `class 1 group A` would not.
	- Suggested naming convention: `Project X Team 01`
- Technical streams must be named `Technical Stream Group - NAME` (where name is the tech stream name)
- To capture mentor info, if this is not provided via the course config (see examples):
	- Students should be added to a group named `Project XXX – Mentor NAME`, so `NAME` is captured as their project mentor.
	- Students should be added to a group named `Technical Stream YYY – Mentor NAME`, so `NAME` is captured as their tech stream mentor.
	- `NAME` must exactly match the name that mentor has on Moodle as it relies on a lookup.
	- (This would be easier with a mentor grouping rather than group, as the former is easier to set up and maintain, but the code isn't ready for it).

## Other (semi-functional) utilities included
- `enrolment_diff.py`: Compares enrolments between two Moodle user files.
- `marker_extraction.py`: Exports student list with one marker chosen from a list for each student (if they had multiple mentors, and only one is required to mark).
- `peer_marking_allocation.py`: Pseudo-code that could generate peer marking allocations based on some criteria.
- `roster_check.py`: Very basic code to verify student's course stream enrolment against their degree plan.

## Known issues
- headless state of Firefox/geckodriver crashes (on macOS, as of Sept 2021)
- Teams module currently returns nice.name@domain or zID@domain for users, randomly it seems, making identification harder as it requires a lookup against known emails to get zIDs. It makes it harder to reliably deal with people on Teams but not (yet) on Moodle.

## TO DO
- Mask password in plain text terminal output on ConnectTeams login step
- Add automatic ability to recognise Connect-MicrosoftTeams login account (zID) and add this to exclusion IDs to avoid accidental self-removal?
	- alt idea: if this is actually desired, have a prompt to check and get approval -> add a current_user variable to check against
- Error handling
	- errors should go into the log
	- data output is unpredictable with ConvertToJson enabled but can cause crashes, so need to catch this properly in all cases
- Integrate `user_stafflist` into default `user_list`
	- Requires easy way to filter out staff and students when desired
- Make `find_users` method more generic
	- ability to search for any variable by its name (as User class vars may increase in the future)
	- `exact=true` as method parameter rather than separate search type
	- Look into custom filter function for python object lists/dicts (a la javascript array.filter function)
	- Alternatively, because sql queries are powerful, it may be efficient to build a db on import. This method then becomes a query execution.
- Allow searching by class id AND group(ing) data.
	- a filter function might ideally take 2+ search terms
	- current `find_users` method could be chained to achieve multiple search terms in `x AND y` fashion, not `OR` or `ANY`.
- Login procedure for some of the classes is the same so standardise, or make a base class for them
	- MoodleBrowser may be a suitable candidate?
- Split TeamsUpdater class into two separate classes:
	- One becomes just a wrapper for the MSTeams powershell module (name: TeamsModuleWrapper?)
	- Another for importing/exporting/managing student/staff lists -> easier to adopt elsewhere
- Do not require input path for TeamsUpdater class (work that into the import function)
- Split classes out into separate files, making it more like a library?
- Export groups and groupings (and perhaps other variables) into students csv
