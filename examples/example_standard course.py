#!/usr/bin/python3

"""
Standard course example, with students spread across multiple workshops (our term for tutorials).

Most complexity rests with the configuration of the course info (the `m3k` variable and all its details),
the course_updater classes and methods take care of most complexity behind the scenes.
"""

from teams_updater import User, TeamsUpdater, MoodleUpdater, LoginData

# basic data on streams and classes
m3k = {
	'MMAN3000': {
		'path'        : 'mman3000-professional-engineering---2021-t2.csv',
		'course_code' : 'MMAN3000',
		'year'        : 2021,
		'term'        : 2,
		'moodle_id'   : 62662,
		'coordinators': ['z1234567', 'z1234567', 'z1234567', 'z1234567', 'z1234567'],
		'streams_data': {
			'MMAN': {
				'coordinators': ['z1234567'],
				'other_owners': ['z1234567'],
				'team_id': '26aad404-6868-4983-9cf1-45154d857ec9',
				'main_class_id': 7550,
				'classes': [
					{'name': 'Workshop_F10A', 'class_id': 7551, 'channel': 'private', 'description': 'Fri 10-12 (Quad G034)',     'instructors': ['z1234567']},
					{'name': 'Workshop_F10B', 'class_id': 7552, 'channel': 'private', 'description': 'Fri 10-12 (TETB G16)',      'instructors': ['z1234567']},
					{'name': 'Workshop_F10C', 'class_id': 7553, 'channel': 'private', 'description': 'Fri 10-12 (Online)',        'instructors': ['z1234567']},
					{'name': 'Workshop_F12A', 'class_id': 7554, 'channel': 'private', 'description': 'Fri 12-14 (Ainsworth 201)', 'instructors': ['z1234567']},
					{'name': 'Workshop_F12B', 'class_id': 7555, 'channel': 'private', 'description': 'Fri 12-14 (Ainsworth G01)', 'instructors': ['z1234567']},
					{'name': 'Workshop_F12C', 'class_id': 7556, 'channel': 'private', 'description': 'Fri 12-14 (Online)',        'instructors': ['z1234567']},
					{'name': 'Workshop_F14A', 'class_id': 7557, 'channel': 'private', 'description': 'Fri 14-16 (Civil Eng 701)', 'instructors': ['z1234567']},
					{'name': 'Workshop_F14B', 'class_id': 7558, 'channel': 'private', 'description': 'Fri 14-16 (Online)',        'instructors': ['z1234567']},
					{'name': 'Workshop_F14C', 'class_id': 7559, 'channel': 'private', 'description': 'Fri 14-16 (Online)',        'instructors': ['z1234567']},
					{'name': 'Workshop_F16A', 'class_id': 7560, 'channel': 'private', 'description': 'Fri 16-18 (Online)',        'instructors': ['z1234567']},
				],
				'channels': [
					{'name': 'Forum',           'channel': 'public',  'description': 'A place for student discussion, asking questions, etc.'},
					{'name': 'z_Demonstrators', 'channel': 'private', 'description': 'Private channel for demonstrator discussions', 'owners': {'list': 'stream_owners'}}
				]
			}
		}
	}
}

if __name__ == '__main__':
	login = LoginData()

	# set to False when skipping Moodle
	if (True):
		with MoodleUpdater(m3k['moodle_id'], login.username, login.password) as mu:
			# ensure any new/changed enrolments are reflected in assigned groups
			mu.auto_create_groups(group_by_type='Class ID', grouping_name='Students Grouping (All)')

			# download fresh user data, overwriting the path variable so that gets picked up below
			m3k['path'] = mu.get_users_csv()

			# get grouping data
			mu.get_grouping_data( m3k['path'] )
	
	# set to False when skipping Teams
	if (True):
		with TeamsUpdater(m3k['path'], username=login.username, password=login.password) as tu:
			# first, import and parse Moodle csv data
			tu.import_user_list(m3k['course_code'], m3k['coordinators'], m3k['streams_data'])

			# generate student list for TSAs, ELS, etc
			tu.export_student_list(replace_terms={
				'Project'    : 'School',
				'Mentor'     : 'Demonstrator',
				'Tech stream': 'Lab'
			})
			# generate a class list, holding relevant instructor and demonstrator data
			#   useful for myExperience, Special Consideration, etc.
			tu.export_class_list(d3k['streams_data'])

			# create and sync teams and channels
			# set to False to skip
			if (False):
				for stream in m3k['streams_data']:
					# most complexity of creating and syncing channels is handled within this method
					#  simplifies the rollover from term to term and eases code maintenance
					team_info = tu.convenience_course_stream_update(
						team_name               = f"{m3k['course_code']} - {m3k['year']} T{m3k['term']}",
						stream_name             = stream,
						stream_data             = m3k['streams_data'][stream],
						course_owners           = 'Design Next',  # base owners for early access
						include_staff           = True,           # whether to include stream staff or just work with base staff
						sync_staff              = True,           # sync staff membership to team and all private channels
						sync_students           = True,           # sync student membership to associated private channels
						remove_staff_allowed    = True,           # if False, staff are added but not removed
						remove_students_allowed = True            # if False, students are added but not removed
					)
