#!/usr/bin/python3

"""
This example covers two courses in one config file, showing how two courses can share one Moodle and Teams login to speed things up.

Each course is handled within its own blocks, and the setup for both courses is considerably different.

ENGG1000 is a large-scale course that runs several projects and streams within the course.
Each student is a member of one project and one tech stream, chosen after term starts (so there's no enrolment data that informs project choice).

DESN2000, despite having separate streams, runs as mostly separate courses.
Each stream could be considered an independent course with some common elements shared with the other streams.

A regular course (see other example files) is essentially like DESN2000 but with a single stream.
"""

from course_updater import User, Logger, PowerShellWrapper, TeamsUpdater, MoodleBrowser, MoodleUpdater, LoginData

# config info per course
e1k = {
	'path'          : 'engg1000-engineering-design---2021-t3.csv',
	'course_code'   : 'ENGG1000',
	'year'          : 2021,
	'term'          : 3,
	'moodle_id'     : 62574,
	'common_team_id': 'edc15965-3789-437a-9085-2b2f8c0a9423',
	'coordinators'  : ['z1234567','z1234567','z1234567'],
	'project_list'  : {
		'Purple House':    {'coordinators': ['z1234567']},
		'R2R':             {'coordinators': ['z1234567']},
		'Bridge to Share': {'coordinators': ['z1234567']},
		'Solar Cable Car': {'coordinators': ['z1234567']}
	},
	'tech_stream_list': {
		'Mechanical':      {'coordinators': ['z1234567','z1234567']},
		'Electrical':      {'coordinators': ['z1234567']},
		'Computing' :      {'coordinators': ['z1234567']},
		'Chemical'  :      {'coordinators': ['z1234567']}
	}
}

d2k = {
	'path'        : 'desn2000-engineering-design-and-professional-practice---2021-t3.csv',
	'course_code' : 'DESN2000',
	'year'        : 2021,
	'term'        : 3,
	'moodle_id'   : 62662,
	'coordinators': ['z1234567','z1234567','z1234567'],
	'streams_data': {
		'PTRL': {
			'coordinators': ['z1234567'],
			'other_owners': [],
			'team_id': '5ba788be-fc47-4195-9004-a19b0026ea6c',
			'main_class_id': 9255,
			'classes': [
				{'name': 'LE1_PTR1',      'class_id': 9254, 'channel': False,    'description': 'Tue 15-18# (Online)',                         'instructors': ['z1234567']},
				{'name': 'LE2_PTR2',      'class_id': 9255, 'channel': False,    'description': 'Tue 12# (w1-3,7-8, Online)',                  'instructors': ['z1234567','z1234567','z1234567']},
				{'name': 'Workshop_H09A', 'class_id': 9246, 'channel': 'public', 'description': 'Thu 09-11 (Block G13); Fri 11-13 (Law 202)',  'instructors': ['z1234567']},
				# {'name': 'Workshop_H12B', 'class_id': 9249, 'channel': False,    'description': 'Thu 12-14 (Sqhouse203); Fri 14-16 (Law 201)', 'instructors': []}
			],
			'channels': [
				{'name': 'Forum',           'channel': 'public',  'description': 'A place for student discussion, asking questions, etc.'},
				{'name': 'z_Demonstrators', 'channel': 'private', 'description': 'Private channel for demonstrator discussions', 'owners': {'list': 'stream_owners'}}
			]
		},
		'MINE': {
			'coordinators': ['z1234567'],
			'other_owners': [],
			'team_id': 'd3c22565-1ff7-40c8-b32a-821d94640320',
			'main_class_id': 9245,
			'classes': [
				{'name': 'LE1_MIN1',      'class_id': 9244, 'channel': False,    'description': 'Tue 14-17# (Online)',                          'instructors': ['z1234567','z1234567']},
				{'name': 'LE2_MIN2',      'class_id': 9245, 'channel': False,    'description': 'Tue 12# (w1-3,7-8, Online)',                   'instructors': ['z1234567','z1234567','z1234567']},
				{'name': 'Workshop_W16E', 'class_id': 9270, 'channel': 'public', 'description': 'Wed 16-18 (Quad 1042); Thu 15-17 (Quad 1042)', 'instructors': ['z1234567']}
			],
			'channels': [
				{'name': 'Forum',           'channel': 'public',  'description': 'A place for student discussion, asking questions, etc.'},
				{'name': 'z_Demonstrators', 'channel': 'private', 'description': 'Private channel for demonstrator discussions', 'owners': {'list': 'stream_owners'}}
			]
		},
		'CEIC': {
			'coordinators': ['z1234567','z1234567'],
			'other_owners': ['z1234567'],
			'team_id': '88233ae9-44ea-4e79-a104-585730146476',
			'main_class_id': 9243,
			'classes': [
				{'name': 'LE1_CHE1',      'class_id': 9242, 'channel': False, 'description': 'Mon 14-16 (w1-3,5-10, Law Th G04)', 'instructors': ['z1234567','z1234567']},
				{'name': 'LE2_CHE2',      'class_id': 9243, 'channel': False, 'description': 'Tue 12# (w1-3,7-8, Online)',        'instructors': ['z1234567','z1234567','z1234567']},
				{'name': 'Workshop_M09A', 'class_id': 9776, 'channel': False, 'description': 'Mon 09-13 (w1-3,5-10, Quad G025)',  'instructors': ['z1234567','z1234567','z1234567']},
				{'name': 'Workshop_M09B', 'class_id': 9777, 'channel': False, 'description': 'Mon 09-13 (w1-3,5-10, Quad G026)',  'instructors': ['z1234567','z1234567','z1234567']},
				{'name': 'Workshop_M09C', 'class_id': 9778, 'channel': False, 'description': 'Mon 09-13 (w1-3,5-10, Quad G027)',  'instructors': ['z1234567','z1234567','z1234567']},
				{'name': 'Workshop_M09D', 'class_id': 9779, 'channel': False, 'description': 'Mon 09-13 (w1-3,5-10, Quad G040)',  'instructors': ['z1234567','z1234567','z1234567']},
				# {'name': 'Workshop_M09E', 'class_id': 9780, 'channel': False, 'description': 'Mon 09-13 (w1-3,5-10, Quad G053)',  'instructors': []}
			],
			'channels': [
				# {'name': 'Forum',           'channel': 'public',  'description': 'A place for student discussion, asking questions, etc.'},
				{'name': 'z_Demonstrators', 'channel': 'private', 'description': 'Private channel for demonstrator discussions', 'owners': {'list': 'stream_owners'}}
			]
		},
		'SPREE': {
			'coordinators': ['z1234567'],
			'other_owners': [],
			'team_id': 'd397ee4e-60f5-4d99-af1e-a61521ef93d7',
			'main_class_id': 9241,
			'classes': [
				{'name': 'LE1_SPR1',      'class_id': 9240, 'channel': False,    'description': 'Mon 14-16# (w1-3,5,10, Online); Thu 15-17# (w1-5, Online)', 'instructors': ['z1234567']},
				{'name': 'LE2_SPR2',      'class_id': 9241, 'channel': False,    'description': 'Tue 12# (w1-3,7-8, Online)',                                'instructors': ['z1234567','z1234567','z1234567']},
				{'name': 'LAB_W11A',      'class_id': 9264, 'channel': 'public', 'description': 'Wed 11-14 (TETB LG09)',   'instructors': ['z1234567','z1234567','z1234567']},
				{'name': 'Workshop_H11A', 'class_id': 9247, 'channel': False,    'description': 'Thu 11 (TETB LG09)',      'instructors': ['z1234567','z1234567','z1234567']},
				{'name': 'Workshop_H12A', 'class_id': 9248, 'channel': False,    'description': 'Thu 12 (TETB LG09)',      'instructors': ['z1234567','z1234567','z1234567']},
				# {'name': 'Workshop_H13A', 'class_id': 9250, 'channel': False,    'description': 'Thu 13 (TETB LG09)',      'instructors': []}
			],
			'channels': [
				{'name': 'Forum',           'channel': 'public',  'description': 'A place for student discussion, asking questions, etc.'},
				{'name': 'z_Demonstrators', 'channel': 'private', 'description': 'Private channel for demonstrator discussions', 'owners': {'list': 'stream_owners'}}
			]
		},
		'MECH': {
			'coordinators': ['z1234567'],
			'other_owners': ['z1234567','z1234567'],
			'team_id': '11a4b57b-f94e-4637-810d-b3518bd5fe48',
			'main_class_id': 9239,
			'classes': [
				{'name': 'LE1_MEC1',      'class_id': 9238, 'channel': False,     'description': 'Mon 14-16# (w1-3,5,7-9, Online); Wed 13# (w2-5,7-9, Online)', 'instructors': ['z1234567','z1234567','z1234567']},
				{'name': 'LE2_MEC2',      'class_id': 9239, 'channel': False,     'description': 'Tue 12# (w1-3,7-9, Online)',                                  'instructors': ['z1234567','z1234567','z1234567']},
				{'name': 'Workshop_H15A', 'class_id': 9251, 'channel': 'private', 'description': 'Thu 15-17 (AinswthG01); Fri 11-13 (Ainswth201)',              'instructors': ['z1234567']},
				{'name': 'Workshop_H15B', 'class_id': 9252, 'channel': 'private', 'description': 'Thu 15-17 (Mat 108); Fri 11-13 (Law 163)',                    'instructors': ['z1234567']},
				# {'name': 'Workshop_H15C', 'class_id': 9253, 'channel': 'private', 'description': 'Thu 15-17 (Ainswth101); Fri 11-13 (Webst 251)',               'instructors': []},
				{'name': 'Workshop_T10A', 'class_id': 9256, 'channel': 'private', 'description': 'Tue 10-12 (ElecEngG10); Thu 09-11 (Quad G047)',               'instructors': ['z1234567']},
				{'name': 'Workshop_T10B', 'class_id': 9257, 'channel': 'private', 'description': 'Tue 10-12 (Quad 1047); Thu 09-11 (ElecEngG03)',               'instructors': ['z1234567']},
				{'name': 'Workshop_T14A', 'class_id': 9258, 'channel': 'private', 'description': 'Tue 14-16 (AinswthG01); Fri 09-11 (Ainswth201)',              'instructors': ['z1234567']},
				{'name': 'Workshop_T14B', 'class_id': 9259, 'channel': 'private', 'description': 'Tue 14-16 (ElecEngG04); Fri 09-11 (Webst 251)',               'instructors': ['z1234567']},
				{'name': 'Workshop_T14C', 'class_id': 9260, 'channel': 'private', 'description': 'Tue 14-16 (JGoodsLG19); Fri 09-11 (Quad 1048)',               'instructors': ['z1234567']},
				# {'name': 'Workshop_T14D', 'class_id': 9261, 'channel': 'private', 'description': 'Tue 14-16 (Law 111); Fri 09-11 (Quad G047)',                  'instructors': []},
				{'name': 'Workshop_W09A', 'class_id': 9262, 'channel': 'private', 'description': 'Wed 09-11 (Ainswth101); Fri 13-15 (Ainswth201)',              'instructors': ['z1234567']},
				# {'name': 'Workshop_W09B',s 'class_id': 9263, 'channel': 'private', 'description': 'Wed 09-11 (ElecEngG10); Fri 13-15 (Quad G047)',               'instructors': []},
				{'name': 'Workshop_W14A', 'class_id': 9265, 'channel': 'private', 'description': 'Wed 14-16 (Mat 232); Thu 11-13 (Mat 232)',                    'instructors': ['z1234567']},
				{'name': 'Workshop_W16A', 'class_id': 9266, 'channel': 'private', 'description': 'Wed 16-18 (Ainswth201); Thu 13-15 (AinswthG01)',              'instructors': ['z1234567']},
				{'name': 'Workshop_W16B', 'class_id': 9267, 'channel': 'private', 'description': 'Wed 16-18 (Ainswth101); Thu 13-15 (Ainswth101)',              'instructors': ['z1234567']},
				{'name': 'Workshop_W16C', 'class_id': 9268, 'channel': 'private', 'description': 'Wed 16-18 (Law 301); Thu 13-15 (Law 203)',                    'instructors': ['z1234567']},
				{'name': 'Workshop_W16D', 'class_id': 9269, 'channel': 'private', 'description': 'Wed 16-18 (Mat 230); Fri 15-17 (ElecEngG04)',                 'instructors': ['z1234567']}
			],
			'channels': [
				{'name': 'Forum',           'channel': 'public',  'description': 'A place for student discussion, asking questions, etc.'},
				{'name': 'z_Demonstrators', 'channel': 'private', 'description': 'Private channel for demonstrator discussions', 'owners': {'list': 'stream_owners'}}
			]
		}
	}
}

if __name__ == '__main__':
	login = LoginData()
	
	# we're using a common Logger object to get all logs combined into one file
	#   so it's created here and reused whenever needed
	with Logger() as logger:
		
		# ----- STEP 1 – Moodle -----
		
		# set to False to skip the Moodle step altogether
		if (False):
			# create a common MoodleBrowser object that we reuse for each course below
			#   it assumes we're logging in with the same user for all courses, so doing it once saves considerable time
			with MoodleBrowser(login.username, login.password, logger=logger) as mb:
				
				# set to False to skip the Moodle step for ENGG1000
				if (False):
					logger.confirm('ENGG1000 ~~~ Moodle update')

					# create MoodleUpdater object for this course, using the common objects created earlier
					with MoodleUpdater(e1k['moodle_id'], browser=mb, logger=logger) as mu:
						# ensure any new/changed enrolments are reflected in assigned groups
						#   this would need to be set up manually once so there's a grouping that can be referred to here
						if (False):
							mu.auto_create_groups(group_by_type='Class ID', grouping_name='Students Grouping - All')

						if (True):
							# download fresh user data, overwriting the my_path variable so that gets picked up below
							my_path = mu.get_users_csv()

							# get grouping data
							#   this goes into another file on download but the two downloaded files are combined on import later on
							mu.get_grouping_data( e1k['path'] )

						# generate a basic groups import file
						#   run once and then manually upload the created csv file to Moodle 'import groups' page before adding page sections
						#   this is essentially a timesaver to quickly get many commonly used groups and groupings
						if (False):
							mu.export_default_groups_list(e1k['project_list'], e1k['tech_stream_list'], replace_terms={
								'Students': 'Project',
								'Student' : 'Project'
							})

						# setup gradebook (run only once)
						#   saves time by setting up gradebook categories based on known projects and tech streams
						if (False):
							mu.add_gradebook_category({
								'name'       : 'COMMON (20%)',
								'id'         : 'FAC',
								'aggregation': 'Weighted mean of grades',
								'grade_max'  : 100,
								'weight'     : 0.2
							})
							mu.add_gradebook_category({
								'name'       : 'PROJECT (60%)',
								'id'         : 'PROJ',
								'aggregation': 'Highest grade',
								'grade_max'  : 100,
								'weight'     : 0.6
							})
							mu.add_gradebook_category({
								'name'       : 'TECHNICAL STREAM (20%)',
								'id'         : 'TECH',
								'aggregation': 'Highest grade',
								'grade_max'  : 100,
								'weight'     : 0.2
							})
							mu.add_gradebook_category({
								'name'       : 'Not assessed and hidden',
								'aggregation': 'Lowest grade',
								'weight'     : 0
							})
							
							for project in e1k['project_list']:
								mu.add_gradebook_category({
									'name'           : f'{project}',
									'aggregation'    : 'Weighted mean of grades',
									'grade_max'      : 100,
									'parent_category': 'PROJECT (60%)'
								})

							for tech_stream in e1k['tech_stream_list']:
								mu.add_gradebook_category({
									'name'           : f'{tech_stream} technical stream',
									'aggregation'    : 'Weighted mean of grades',
									'grade_max'      : 100,
									'parent_category': 'TECHNICAL STREAM (20%)'
								})

						# setup sections (run only once)
						#   to get access restrictions right, it needs Moodle to have the right groups/groupings
						if (False):
							# start by removing default weekly sections
							for x in range(1,11):
								mu.remove_section(f'Week {x}')

							# add sections
							mu.add_section({'name': 'Common - Lectures'})
							mu.add_section({'name': 'Common - Impromptu Design Day + Reflective Writing Task'})
							mu.add_section({'name': 'Common - Project selection'})
							mu.add_section({'name': 'Common - Technical stream selection'})
							mu.add_section({'name': 'Common - EDP: Engineering Design Process'})
							mu.add_section({'name': 'Common - Resources'})

							mu.add_section({
								'name': 'Projects',
								'restrictions': [
									{'group': 'Staff (DO NOT REMOVE)'}
								]
							})
							for project in e1k['project_list']:
								mu.add_section({
									'name': f'Project - {project}',
									'restrictions': [
										{'grouping': f'Project Grouping - {project}'}
									]
								})

							mu.add_section({
								'name': 'Technical streams',
								'restrictions': [
									{'group': 'Staff (DO NOT REMOVE)'}
								]
							})
							for tech_stream in e1k['tech_stream_list']:
								mu.add_section({
									'name': f'Technical stream - {tech_stream}',
									'restrictions': [
										{'grouping': f'Technical Stream Grouping - {tech_stream}'}
									]
								})

							mu.add_section({'name': 'Staff (hidden)', 'hidden': True})

				# set to False to skip the Moodle step for DESN2000
				if (True):
					logger.confirm('DESN2000 ~~~ Moodle update')

					with MoodleUpdater(d2k['moodle_id'], browser=mb, logger=logger) as mu:
						# ensure any new/changed enrolments are reflected in assigned groups
						if (False):
							mu.auto_create_groups(group_by_type='Class ID', grouping_name='Students Grouping (All)')

						if (True):
							# download fresh user data, overwriting the d2k.path variable so that gets picked up below
							d2k['path'] = mu.get_users_csv()

							# get grouping data
							mu.get_grouping_data( d2k['path'] )

						# get grouping data
						#   this goes into another file on download but the two downloaded files are combined on import later on
						if (False):
							mu.export_default_groups_list(d2k['streams_data'])

						# setup gradebook
						if (False):
							mu.add_gradebook_category({
								'name'       : 'DESIGN JOURNAL (25%)',
								'id'         : 'JOURN',
								'aggregation': 'Weighted mean of grades',
								'grade_max'  : 100,
								'weight'     : 0.25
							})
							mu.add_gradebook_category({
								'name'       : 'DESIGN PRESENTATION (15%)',
								'id'         : 'PRES',
								'aggregation': 'Weighted mean of grades',
								'grade_max'  : 100,
								'weight'     : 0.15
							})
							mu.add_gradebook_category({
								'name'       : 'SCHOOL ASSESSMENTS (60%)',
								'id'         : 'SCHOOL',
								'aggregation': 'Highest grade',
								'grade_max'  : 100,
								'weight'     : 0.6
							})
							mu.add_gradebook_category({
								'name'       : 'Not assessed and hidden',
								'aggregation': 'Lowest grade',
								'weight'     : 0
							})
							 
							for stream in d2k['streams_data']:
								mu.add_gradebook_category({
									'name'           : f'{stream} - School assessments',
									'aggregation'    : 'Weighted mean of grades',
									'grade_max'      : 100,
									'parent_category': 'SCHOOL ASSESSMENTS (60%)'
								})

						# setup sections
						if (False):
							# default sections to remove
							for x in range(1,11):
								mu.remove_section(f'Week {x}')

							# add new sections
							mu.add_section({'name': 'Common lectures'})
							mu.add_section({'name': 'Common assessments'})

							for stream in d2k['streams_data']:
								mu.add_section({
									'name': stream,
									'restrictions': [
										{'grouping': f'Students Grouping - {stream}'}
									]
								})

							mu.add_section({'name': 'Staff (hidden)', 'hidden': True})

						# download grades from ongoing assessments (with Workshop (UNSW) tool)
						#   this just makes it easier to track completion rates while the assessment is still open
						#   disable when not required, as it can be really slow on some rows of data
						if (False):
							# pass
							# mu.get_workshop_grades(4165197)
							# mu.get_workshop_grades(4217614)
							# mu.get_workshop_grades(4217633)
							# mu.get_workshop_grades(4217847)
		
		# ----- STEP 2 – Teams -----
		
		# set to False to skip the Teams step altogether
		if (True):
			# create PowerShellWrapper object once to reuse later on (saves time by reusing logins)
			with PowerShellWrapper(lazy_start=True, login_method='credentials', username=login.username, password=login.password) as pw:

				# set to False to skip the Teams step for ENGG1000
				if (True):
					logger.confirm('ENGG1000 ~~~ Teams update')

					# create TeamsUpdater object for this course, reusing the common process and logger objects
					with TeamsUpdater(e1k['path'], process=pw, logger=logger) as tu:
						# first, import and parse Moodle csv data
						tu.import_user_list(e1k['course_code'], e1k['coordinators'], e1k['project_list'], e1k['tech_stream_list'])

						# generate student list for TSAs, ELS, etc
						tu.export_student_list()

						# ----- COMMON TEAM -----

						# Note: The common Team for the course would be created in advance via Central IT to get
						#       automatic syncing with student enrolment data. That takes pressure of having to
						#       run this script very frequently (the auto-enrolment sync runs every few hours).
						
						# create and sync team and channels
						if (False):
							# find common owners
							common_owners    = tu.find_users('group', 'Staff',           tu.user_stafflist)
							impromptu_staff  = tu.find_users('group', 'Staff Impromptu', tu.user_stafflist)

							# get basic team info
							team_info        = tu.get_team(e1k['common_team_id'], get_channels=True)

							# set appearance (run once on setup)
							if (False):
								# set Team name
								team_name   = f"{e1k['course_code']} - {e1k['year']} T{e1k['term']} - Common"
								description = f"Common Team for {e1k['course_code']} - {e1k['year']} T{e1k['term']}"

								if (team_info['DisplayName'] != team_name or team_info['Description'] != description):
									tu.set_team(e1k['common_team_id'], new_name=team_name, description=description)

								# set Team picture (run only once)
								tu.set_team_picture(e1k['common_team_id'], '../Logos/engg1000-general.png')

							# create channels
							#   (if channels already exist, nothing happens so it's safe and not time-intensive to run this every time)
							if (True):
								# add private channels
								if ('Impromptu Staff' not in team_info['channels']):
									tu.create_channel(e1k['common_team_id'], 'Impromptu Staff', 'Private', description='Private channel for impromptu design staff discussions')

							# sync members
							#   in ENGG1000, we only sync users on Moodle in any 'Staff' group as owners of the Team.
							#   note that in T1, staff may be 100+ and Teams only allows 100 owners.
							if (True):
								# update team owners
								tu.update_team(e1k['common_team_id'], common_owners, role='Owner', remove_allowed=True)

								# sync impromptu channel
								#   because not all staff may be on Moodle by week 1, some manual additions may be required too.
								#   That's something the script could handle if there's a separate list with userIDs to add
								#   but generally, it's quicker to just do manually in Teams.
								tu.update_channel(e1k['common_team_id'], 'Impromptu Staff', impromptu_staff)
						
						# ----- OTHER TEAMS: Projects and tech streams -----

						"""
						In the past, we have supported some projects and tech streams by incorporating their
						config and sync needs into our run.

						With this code getting more flexible, it's fairly easy to add in other Teams to sync
						based on the same generic Moodle data. Usually, it would only need the right groups or
						groupings attached to users in Moodle to get something going.
						"""

				# set to False to skip the Teams step for ENGG1000
				if (True):
					logger.confirm('DESN2000 ~~~ Teams update')
					
					# create TeamsUpdater object for this course, reusing the common process and logger objects
					with TeamsUpdater(d2k['path'], process=pw, logger=logger) as tu:
						# import and parse Moodle csv data
						tu.import_user_list(d2k['course_code'], d2k['coordinators'], d2k['streams_data'])

						# generate student list for TSAs, ELS, etc
						#   by default, this method uses ENGG1000 terminology that's somewhat odd so we replace it
						#   as DESN2000 is a more generic course without special slang
						tu.export_student_list(replace_terms={
							'Project'    : 'School',
							'Mentor'     : 'Demonstrator',
							'Tech stream': 'Lab'
						})
						# generate a class list, holding relevant instructor and demonstrator data
						#   useful for myExperience, Special Consideration, etc.
						tu.export_class_list(d2k['streams_data'])

						# create and sync teams and channels
						# set to False to skip
						if (False):
							for stream in d2k['streams_data']:
								# most complexity of creating and syncing channels is handled within this method
								#  simplifies the rollover from term to term and eases code maintenance
								team_info = tu.convenience_course_stream_update(
									team_name               = f"{d2k['course_code']} {stream} - {d2k['year']} T{d2k['term']}",
									stream_name             = stream,
									stream_data             = d2k['streams_data'][stream],
									course_owners           = 'Design Next',  # base owners for early access
									include_staff           = True,           # whether to include stream staff or just work with base staff
									sync_staff              = True,           # sync staff membership to team and all private channels
									sync_students           = True,           # sync student membership to associated private channels
									remove_staff_allowed    = False,          # if False, staff are added but not removed
									remove_students_allowed = True            # if False, students are added but not removed
								)
