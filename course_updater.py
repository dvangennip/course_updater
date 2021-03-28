#!/usr/bin/python3

#####
# script requires python version 3.7+, powershell 7+, and the PS Teams module to be installed
# only tested on MacOS 10.15
#
# generally, this script is as resilient as a toddler with icecream in their hand
# it will drop and create a scene at some stage...
#####

from dataclasses import dataclass, field
# from typing import Dict

import csv
from datetime import datetime
import subprocess
import time
import os
import fcntl
import re
import getpass
from splinter import Browser
import keyring
import json


# for DESN2000
# it it assumed Teams are already created and that students are auto-added to teams via Central IT sync
#	originally, this script was only concerned with keeping private channels in sync with the Moodle list

# make sure that for each tutorial-like ClassItem, there is a corresponding private channel
#	could be done programmatically but channel name is likely hard to form without knowledge of timetable.
#   timetable info can be fed in from classutil website but needs parsing.
#   setting them up manually is very likely to be faster (including adding demonstrators, if that list is short).
#	generating the class list below isn't too time intensive using regex on the classutil list.

# -----------------------------------------------------------------------------

@dataclass
class ClassItem:
	id               : int
	name             : str
	teams_group_id   : str
	course           : str  = ''
	teams_user_list  : dict = field(default_factory=dict)
	desired_user_list: dict = field(default_factory=dict)

	def __getitem__ (self, key):
		return getattr(self, key)

	def __str__ (self):
		if (len(self.course) > 0):
			return f'{self.id} ({self.name} / {self.course})'
		else:
			return f'{self.id} ({self.name})'


@dataclass
class User:
	id       : str
	name     : str
	class_ids: []
	groups   : []
	owner    : bool = False  # 'Member'|'Owner'
	course   : str  = ''
	email    : str  = ''

	def __getitem__ (self, key):
		return getattr(self, key)

	def __str__ (self):
		return f'{self.name} ({self.id})'

	def role (self):
		return ('Member', 'Owner')[self.owner]

	def in_class (self, class_id):
		return (class_id in self.class_ids)

	def in_group (self, group):
		return (group in self.groups)


class LoginData:
	"""
	very basic class that safely stores login data (handy for repeated use).
	once login data is passed, there's no need to repeat it.
	"""
	def __init__ (self, username=None, password=None):
		self.app_id = 'PY_TEAMS_UPDATER'

		self.username = username
		if (self.username is None):
			# try and retrieve first
			self.username = keyring.get_password(self.app_id, 'username_key')

			if (self.username is None):
				# get new username
				self.username = input('Username: ')
			
		if (self.username.find('@') == -1):
			self.username += '@ad.unsw.edu.au'

		# store for later use
		keyring.set_password(self.app_id, 'username_key', self.username)
		
		self.password = password
		if (self.password is None):
			# try and retrieve
			self.password = keyring.get_password(self.app_id, self.username)

			if (self.password is None):
				# get input for a new password
				self.password = getpass.getpass(prompt='Password: ')

		# store
		keyring.set_password(self.app_id, self.username, self.password)


# -----------------------------------------------------------------------------
# default input variables (as examples only here)

""" path to Moodle-exported CSV file """
my_path = 'desn2000-engineering-design---professional-practice---2020-t3.csv'

""" have a list of classes (see for structure the ClassItem class below) """
my_classes_list = [
	ClassItem(1112,  'Demonstrators',  '458b02e9-dea0-4f74-8e09-93e95f93b473', 'DESN2000_2020T3_CVEN'),
]

"""
have a whitelist of users not to be removed from channels (demonstrators, etc)
these users typically will not feature in Moodle-based ClassID lists
this list is also expanded with any staff found in a Moodle user file
"""
my_user_whitelist = []


# -----------------------------------------------------------------------------


class PowerShellWrapper:
	"""
	this is what happens when you know python and think you'll just call
	some powershell commands, only to realise when you're in knee-deep that
	the login step requires the shell process to stay alive between calls
	and now you have to tame powershell somehow, making you wonder if simply
	learning powershell in the first place wouldn't have been a better bet...
	
	handles powershell commands in the background, works kind of like the
	`pexpect` library, only returning when it encounters the reappearing prompt
	or another string in the output that we want to stop at.
	
	very simple, very likely not to work with most edge cases.
	"""
	def __init__ (self, debug=True):
		self.latest_output      = ''
		self.connected_to_teams = False
		self.count              = 0
		self.debug_mode         = debug

		self.process = subprocess.Popen(
			['pwsh'],
			stdin    = subprocess.PIPE,
			stdout   = subprocess.PIPE,
			stderr   = subprocess.STDOUT,
			encoding = 'utf-8'
		)
		fcntl.fcntl(self.process.stdout.fileno(), fcntl.F_SETFL, os.O_NONBLOCK)

		if (self.debug_mode):
			self.log = open('cmd_logs/alog.txt', 'w')

		# run a few commands as a self test
		time.sleep(5)
		self.run_command('nothing - just letting it settle', False)
		time.sleep(5)
		self.run_command('Write-Output "check"')

	# so we can use the with statement
	def __enter__ (self):
		return self

	# so we can exit after using the with statement
	def __exit__ (self, type, value, traceback):
		self.close()

		if (traceback is None):  # no exception occured
			pass
		else:
			return False  # re-raises the exception on return to be transparent

	def close (self):
		# disconnect and confirm any prompts that may come our way
		if (self.connected_to_teams):
			self.run_command('Disconnect-MicrosoftTeams')

		self.process.stdin.close()
		self.process.kill()

		if (self.debug_mode):
			self.log.close()

	def run_command (self, command, do_run=True, delay=0.5, return_if_found=None, convert_json=False):
		"""
		The shakily beating heart of this wrapper.
		It takes a command and feeds that into the powershell process, parsing any output it generates.

		This method returns whenever it re-encounters the command prompt, usually the signal a command was processed.
		Alternatively, passing a string to `return_if_found` will stop once that string is encountered in the process output.

		Set `convert_json` to True when expecting output that needs parsing.
		"""

		self.count += 1

		# check command and do final alterations
		command = command
		if (convert_json):
			command += ' | ConvertTo-Json'  # generates output object in JSON format

		# send command to process
		if (do_run == True):
			if (self.debug_mode):
				print(f'\nCOMMAND: {command}')
				print('---------------------------------------')
			
			self.process.stdin.write(command + os.linesep)  # line separator is needed to get it executed
			self.process.stdin.flush()

		# READ OUTPUT -------------------

		output = ''

		if (do_run):
			# give things some time to settle
			time.sleep(delay)

			while True:
				try:
					# read stdout line by line
					# this makes it easier to pick up significant bits of data
					o = self.process.stdout.readline()

					if re.match('PS .+?>\s{0,1}$', o) is not None:
						if (self.debug_mode):
							self.log.write('\n~~~~ REGEX MATCH - BREAKING LOOP ~~~~\n')
						break
					elif (o == command or o == command + '\n'):  # linefeed is usually added
						if (self.debug_mode):
							self.log.write(f'\n~~~ skipping command line: {command} ~~~\n')
						# pass  # no need to save this
					else:
						output += o
						if (self.debug_mode):
							print(o, end='')  # avoid double linefeeds when printing
							
							self.log.write(o)

					# check for this after o is added to output
					if (return_if_found is not None and o.find(return_if_found) != -1):
						if (self.debug_mode):
							self.log.write('\n~~~ found return string ~~~\n' )
						break

				except TypeError:  # raised when a NoneType shows up, effectively signalling an empty buffer
					time.sleep(0.1)
				except IOError:    # also signals an empty buffer
					time.sleep(0.1)
		else:
			# return early to avoid getting stuck in loop below (there's no real output anyway)
			return output

		# if output is a oneliner - negates the need for more parsing for simple responses
		if (re.match('^.+?\n', output)):
			output = output.replace('\n','')
		
		if (convert_json):
			if (len(output) > 0 and output.lower().find('error occurred while executing') == -1):
				output = json.loads(output)
			# else just keep output unconverted

		self.latest_output = output

		# log command and output data for debugging purposes
		if (self.debug_mode):
			with open(f'cmd_logs/cmd_{self.count}.txt','w') as f:
				f.write(f'COMMAND: {command}\n\n')
				f.write(str(output))   # making sure this is always a string

		return output

	def connect_to_teams (self, login_method='popup', username=None, password=None):
		"""
		Running any commands from the MicrosoftTeams pwoershell module requires an active login
		This method logs in automatically, either by just giving a popup or by attempting a fully
		automatic login by hiding the Office365 login process via a headless browser connection.

		TODO: automated seems broken in some cases at the moment... still opens browser tab that works.
		"""
		if (self.connected_to_teams):
			return True
		else:
			response = ''

			if (login_method == 'popup' or login_method == 'default'):
				# login via a browser window/popup - works but needs user input via browser
				response = self.run_command('Connect-MicrosoftTeams')
			else:
				# get username and password
				username = username
				if (username is None):
					username = input('Username: ')
				if (username.find('@') == -1):
					username += '@ad.unsw.edu.au'
				password = password
				if (password is None):
					password = getpass.getpass(prompt='Password: ')

				if (login_method == 'automated'):
					# login via browser window but automate all actions
					try:
						b = Browser('firefox', headless=True)  # by default assumes firefox + geckodriver
						b.visit('https://microsoft.com/devicelogin')

						# begin connecting and get authentication code
						response = self.run_command('Connect-MicrosoftTeams',
							return_if_found='use a web browser to open the page https://microsoft.com/devicelogin and enter the code')

						regex = re.compile('.+enter the code ([a-zA-Z0-9]{9}) to authenticate.+')
						r = regex.search(response)

						authentication_code = r.groups()[0]
						print(f'Using authorisation code: {authentication_code}')

						# fill in authentication code in text field
						b.fill('otc', authentication_code)
						# click next
						b.find_by_id('idSIButton9').click()
						# wait for next page
						time.sleep(3)

						# assume we're on a clean slate login (no history or existing login)

						# fill in username
						b.fill('loginfmt', username)
						b.find_by_id('idSIButton9').click()
						# wait for next page
						time.sleep(2)

						# second up, password
						b.fill('passwd', password)
						b.find_by_id('idSIButton9').click()
						time.sleep(4)

						# check if we are now logged in
						if (not b.is_text_present('You have signed in to the MS Teams Powershell Cmdlets application')):
							print('WARNING: devicelogin may have failed')

						# continue the login process and fetch final response
						response = self.run_command('just want to see more output', False, delay=3)
						
						b.quit()
					except Exception as e:
						print(e)
				elif (login_method == 'credentials'):
					# note: this procedure doesn't work because basic authentication uni tenant doesn't support the right sign-on protocols
					#       would be cool though...

					# get login details
					username = username
					if (username is None):
						username = input(r'Domain\Username: ')

					password = password
					if (password is None):
						password = getpass.getpass(prompt='Password: ')

					# first, setup a credential object based on login details
					self.run_command(f'$User = "{username}"')
					self.run_command(f'$PWord = ConvertTo-SecureString -String "{password}" -AsPlainText -Force')
					self.run_command('$Credential = New-Object -TypeName System.Management.Automation.PSCredential -ArgumentList $User, $PWord')
					
					# use credentials to connect (avoids a user prompt)
					response = self.run_command('Connect-MicrosoftTeams -Credential $Credential')
			
			# check for succesful connection
			if (response.find('Token Acquisition finished successfully. An access token was returned')):
				self.connected_to_teams = True

			return self.connected_to_teams

	# TODO: not used at the moment
	def parse_common_errors (self, input_string=''):
		# TODO check for typical errors
		if (input_string.find('You must call the Connect-MicrosoftTeams cmdlet before calling any other cmdlets.')):
			return False


class TeamsUpdater:
	"""
	Wrapper around powershell teams commands, with additional logic to keep teams and channels in sync with an external list.
	"""
	def __init__ (self, path=None, classes={}, whitelist={}, process=None):
		# open log file
		self.log_file = open('teams_updater.log', 'a')
		self.log_file.write('\n\n\n~~~ NEW LOG ~~~ ~~~ ~~~ ~~~')

		# init variables
		self.data_path       = path
		if (self.data_path is None):
			self.log('Please provide a filepath to a CSV file that TeamsUpdater can read.', 'WARNING')
			# raise FileNotFoundError

		# create whitelist from input list
		# note that the list isn't technically a list but rather a dictionary
		# dicts have the benefit that we can match by id/key value rightaway
		# not optimal from a neatness point of view but it works fine
		self.user_whitelist  = {}
		for name in whitelist:
			self.user_whitelist[str(name.id)] = name

		# master user list (idem, a dict not a list)
		self.user_list       = {}

		# TODO DEPRECATE legacy classes list
		self.classes_list    = {}
		for cl in classes:
			self.classes_list[str(cl.id)] = cl

		# use existing external process to connect to powershell or create new one
		if (process is not None):
			self.process = process
		else:
			self.process = PowerShellWrapper()
	
	def __enter__ (self):
		""" enables the use of the `with` statement (`with TeamsUpdater() as tu:`) """
		return self

	def __exit__ (self, type, value, traceback):
		""" so we can exit after using the `with` statement """
		self.close()

		if (traceback is None):  # no exception occured
			pass
		else:
			return False  # re-raise the exception to be transparent
	
	def connect (self, login_method='default', username=None, password=None):
		""" most commands require an authenticated session, so connect early to avoid later failures """
		self.connected = self.process.connect_to_teams(login_method=login_method, username=username, password=password)

	def close (self):
		"""
		cleanup any open connections, files open
		"""
		if (self.process is not None):
			self.process.close()
		self.log_file.close()

	def import_user_list (self):
		"""
		Imports a user list csv file that was exported from Moodle
		"""
		self.log(f'Importing data from: {self.data_path}')

		unknown_class_ids = []

		count_total       = 0
		count_instructors = 0
		count_students    = 0
		count_unknown     = 0
		
		# open and read CSV file - assumes existence of columns named Username (for zID), First Name, Surname, and a few more
		with open(self.data_path) as fs:
			filereader = csv.DictReader(fs)

			# for every user (a row in csv file), add them to the known class lists
			for user in filereader:
				user_id = user['Username'].lower()  # make sure it's all lowercase, for later comparisons

				# parse class IDs and convert comma-separated field to a list of int values
				class_ids = []
				if (user['Class ID'] != '-'):
					class_ids = list(map(int, user['Class ID'].split(',')))

				# parse groups
				user_groups = []
				for n in range(1,50):
					g = user[f'Group{n}']
					# empty values are represented as float(nan) but we only care about strings anyway, so just test for that
					if (g is not None and type(g) is str and len(g) > 0):
						user_groups.append(g)

				new_user = User(
					user_id,
					user['First name'] + ' ' + user['Surname'],
					class_ids,
					user_groups
				)
				# TODO integrate into above
				new_user.email = user['Email address']

				# users without classes assigned get added to the whitelist
				# in Moodle, more or less by definition, no ClassID -> staff
				if (user['Class ID'] == '-'):
					# do another check to make sure this user is actually staff
					#   adding a user to this group requires manual assignment in Moodle
					#   as an alternative, you can add them into the user whitelist passed in at the start
					if (new_user.in_group('Staff (DO NOT REMOVE)')):
						new_user.owner = True

						# don't overwrite prior whitelist user data
						if (user_id not in self.user_whitelist.keys()):
							self.user_whitelist[user_id] = new_user

						count_instructors += 1
					else:
						self.log(f'User {new_user} has no Class IDs but is not a staff member: skipped.', 'WARNING')
						count_unknown += 1
				else:
					# add new to master list
					self.user_list[user_id] = new_user

					# TODO DEPRECATE now, iterate over the found class IDs and add the user to its list
					for class_id in class_ids:
						if (str(class_id) in self.classes_list.keys()):
							# overwrite, likely 
							self.classes_list[str(class_id)]['desired_user_list'][user_id] = new_user
						else:
							# add class_id to list of unknown classes - useful feedback in case a class is missing by accident
							if (class_id not in unknown_class_ids):
								unknown_class_ids.append(class_id)
							else:
								pass  # ignore any later encounters

					count_students += 1

		# sort the unknown class ids from low to high for readability
		unknown_class_ids.sort()
		self.log(f'No class items that match Class IDs {", ".join(map(str, unknown_class_ids))}')

		count_total = count_students + count_instructors + count_unknown
		self.log(f'Imported data on {count_total} users (students: {count_students}, instructors: {count_instructors}, unknown: {count_unknown}).\n\n')

	def export_student_list (self, project_list, tech_stream_list=None):
		""" Exports a list of students with project (and optional tech stream) information """

		# assume course code is first thing in path, for example: engg1000-title-2021-t1.csv
		course = self.data_path[:self.data_path.find('-')]
		
		output_path = self.data_path.replace('.csv', '-students.csv')

		with open(output_path, 'w') as f:
			# header
			f.write('Student zID,Student name,Email address,Class IDs,Course,Course coordinator,Course coordinator zID,Course coordinator email,Project,Project coordinator,Project coordinator zID,Project coordinator email,Project mentor,Project mentor zID,Tech stream,Tech stream coordinator,Tech stream coordinator zID,Tech stream coordinator email,Tech stream mentor,Tech stream mentor zID')
			
			for sid in self.user_list:
				s = self.user_list[sid]

				# avoid including staff (who have no class ids)
				if (len(s.class_ids) == 0):
					continue

				# TODO generalise this info
				ccoordinator    = 'Ilpo Koskinen, Nick Gilmore, Domenique van Gennip'
				ccoordinator_id = 'z3526743,z3418878,z3530763'
				ccoordinator_em = 'designnext@unsw.edu.au'

				project         = '-'
				pcoordinator    = '-'
				pcoordinator_id = '-'
				pcoordinator_em = '-'

				pmentor         = '-'
				pmentor_id      = '-'
				pmentor_em      = '-'

				tech_stream     = '-'
				tcoordinator    = '-'
				tcoordinator_id = '-'
				tcoordinator_em = '-'

				tmentor         = '-'
				tmentor_id      = '-'
				tmentor_em      = '-'

				for g in s.groups:
					if (g.find('Project Group - ') != -1):
						project = re.sub(
							r'Project Group - (?P<project>.+?) \(.+?\)',  # original
							r'\g<project>',  # replacement
							g  # source string
						)

					# TODO generalise term 'Mentor' or allow 'Demonstrator' as well
					if (g.find('Project') != -1 and g.find('Mentor') != -1):
						pmentor = re.sub(
							r'Project (?P<project>.+?) (- ){0,1}Mentor (?P<mentor>.+?)',
							r'\g<mentor>',
							g
						)
						# funky whitespaces can throw us further down
						pmentor = pmentor.replace(' ', ' ')  # these two 'whitespaces' are not the same...

						# find ID based on name
						for su in self.user_whitelist:
							mu = self.user_whitelist[su]

							# match against lower case to avoid minor spelling issues to cause mismatches
							if (mu.name.lower() == pmentor.lower()):
								pmentor_id = mu.id
								pmentor_em = mu.email

					if (tech_stream_list is not None):
						if (g.find('Technical Stream Group - ') != -1):
							tech_stream = g.replace('Technical Stream Group - ','').replace(' (OnCampus)','').replace(' (Online)','')

						if (g.find('Technical Stream') != -1 and g.find('Mentor') != -1):
							tmentor = re.sub(
								r'Technical Stream (?P<stream>.+?) (- ){0,1}Mentor (?P<mentor>.+?)',
								r'\g<mentor>',
								g
							)
							# funky whitespaces can throw us further down
							tmentor = tmentor.replace(' ', ' ')  # these two 'whitespaces' are not the same...

							# find ID based on name
							if (tmentor != '-'):
								for su in self.user_whitelist:
									mu = self.user_whitelist[su]

									# match against lower case to avoid minor spelling issues to cause mismatches
									if (mu.name.lower() == tmentor.lower()):
										tmentor_id = mu.id
										tmentor_em = mu.email

				if (project != '-'):
					pcoordinator_id = project_list[project]['coordinator']
					pids = pcoordinator_id.split(',')

					for index, pid in enumerate(pids):
						pcoordinator    += ', ' + self.user_whitelist[pid].name
						pcoordinator_em += ', ' + self.user_whitelist[pid].email

						if (index == 0):
							pcoordinator    = pcoordinator.replace('-, ','')
							pcoordinator_em = pcoordinator_em.replace('-, ','')

				if (tech_stream_list is not None and tech_stream != '-'):
					tcoordinator_id = tech_stream_list[tech_stream]['coordinator']
					tids = tcoordinator_id.split(',')

					for index, tid in enumerate(tids):
						tcoordinator    += ', ' + self.user_whitelist[tid].name
						tcoordinator_em += ', ' + self.user_whitelist[tid].email

						if (index == 0):
							tcoordinator    = tcoordinator.replace('-, ','')
							tcoordinator_em = tcoordinator_em.replace('-, ','')

				f.write(f'\n{s.id},{s.name},{s.email},"{",".join(map(str,s.class_ids))}",{course},"{ccoordinator}","{ccoordinator_id}","{ccoordinator_em}",{project},"{pcoordinator}","{pcoordinator_id}","{pcoordinator_em}","{pmentor}","{pmentor_id}",{tech_stream},"{tcoordinator}","{tcoordinator_id}","{tcoordinator_em}","{tmentor}","{tmentor_id}"')

			self.log(f'Exported student list to {output_path}\n\n')


	def create_team (self, name, description='', visibility='Private', owners=[], info=''):
		"""
		Create a new Team. Connected account will become an owner automatically.

		see: https://docs.microsoft.com/en-us/powershell/module/teams/new-team?view=teams-ps
		info parameter isn't used/required for anything but may be useful to parse the logs and keep team data and other info together.
		"""
		
		# TODO improve this by using convert_json = True to get team object in one go
		# create team
		response = self.process.run_command(
			f'$group = New-Team -DisplayName "{name}" -Description "{description}" -Visibility {visibility}'
		)
		# parse response in 2nd step (returns a Group object with GroupID for the newly created team)
		response_group_id = self.process.run_command('$group.GroupId')
		
		# check for correct group_id format: 458b02e9-dea0-4f74-8e09-93e95f93b473
		if (not re.match('^[\dabcdef-]{36}$', response_group_id)):
			self.log(f'Failed to create {visibility.lower()} team {name} (response: {response_group_id}) ({info=})', 'ERROR')
		else:
			self.log(f'Created {visibility.lower()} team {name} ({response_group_id}) ({info=})')

			self.add_users_to_team(response_group_id, owners, 'Owner')

	def get_team_user_list (self, team_id, role='All'):
		"""
		Get list of current users in team
		"""
		role_filter = ''
		if (role != 'All'):
			role_filter = f' -Role {role}'
		
		response = self.process.run_command(
			f'Get-TeamUser -GroupId {team_id}{role_filter}',
			convert_json = True
		)

		# parse response
		# if channel not found, stop
		if (type(response) == 'str' and response.find('Team not found') != -1):
			return False
		else:
			# feed response data into list
			user_list = {}

			for d in response:
				print(d)
				userid = d['User'].lower().replace('@ad.unsw.edu.au','')  # 'User ' = accountname@domain
				user_list[userid] = User(
					userid,     # zID
					d['Name'],  # name       
					[],         # unknown class ids
					[]          # unknown groups
				)

			print(f'USER LIST for {team_id}')
			for k in user_list:
				print(user_list[k])

			return user_list

	def remove_users_from_team (self, team_id, users=[User], role='Member'):
		""" coonvenience function to remove a list of users in one go """
		for u in users:
			self.remove_user_from_team(team_id, u, role)

	def remove_user_from_team (self, team_id, user=User, role='Member'):
		""" removing a user as role='Owner' keeps them as a team member """
		response = self.process.run_command(
			f'Remove-TeamUser -GroupId {team_id} -User {user.id}@ad.unsw.edu.au -Role {role}'
		)

		self.log(f'Team {team_id}: Removed {user} as {role}')

		# TODO check response
		return True

	def add_users_to_team (self, team_id, users=[User], role='Member'):
		""" coonvenience function to add a list of users in one go """
		for u in users:
			self.add_user_to_team(team_id, u, role)

	def add_user_to_team (self, team_id, user=User, role='Member'):
		""" Adds a user to the team. Add an existing member as an `Owner` to elevate their role. """
		response = self.process.run_command(
			f'Add-TeamUser -GroupId {team_id} -User {user.id}@ad.unsw.edu.au -Role {role}'
		)

		self.log(f'Team {team_id}: Added {user} as {role}')

		# TODO check response
		return True

	def update_team (self, team_id, desired_user_list, team_user_list=None):
		""" add/remove users to match the `desired_user_list` """

		count_removed = 0
		count_added   = 0

		team_user_list = team_user_list
		if (team_user_list is None):
			# get the team user list
			team_user_list = self.get_team_user_list(team_id)

		# check current teams list against desired list
		#	remove any not on desired list (but check against whitelist, those are save from deletion)
		for user_in_teams_list in team_user_list:
			if (user_in_teams_list not in desired_user_list and user_in_teams_list not in self.user_whitelist):
				response = self.remove_user_from_team(team_id, team_user_list[user_in_teams_list])
				
				if (response):
					count_removed += 1
				
		# add any not in teams list but on desired list
		for user_in_desired_list in desired_user_list:
			if (user_in_desired_list not in team_user_list):
				response = self.add_user_to_team(team_id, desired_user_list[user_in_desired_list])
				
				if (response):
					count_added += 1

		self.log(f'Updating team {team_id} complete (- {count_removed} / + {count_added})')

		return (count_removed, count_added)

	def create_channel (self, team_id, channel_name, channel_type='Standard', owners=[]):
		# create channel
		response = self.process.run_command(
			f'New-TeamChannel -GroupId {team_id} -DisplayName "{channel_name}" -MembershipType {channel_type}',
			convert_json = True
		)

		# TODO parse response
		# if (response.find(''))

		self.log(f'Created channel {channel_name} in Team {team_id}')

		# if all good, set owners (only relevant for private channels)
		if (channel_type == 'Private'):
			self.add_users_to_channel(team_id, channel_name, owners, role='Owner')

	def get_channels_user_list (self, channels_list):
		""" TODO untested and unused at the moment """
		channels_user_lists = {}
		for ch in channels_list:
			channels_user_lists[ch.name] = self.get_channel_user_list(ch.team_id, ch.name)
		return channels_user_lists

	def get_channel_user_list (self, team_id, channel_name, role='All'):
		""" Get list of current users in channel, and return a dict with user ids as the keys """
		role_filter = ''
		if (role != 'All'):
			role_filter = f' -Role {role}'

		response = self.process.run_command(
			f'Get-TeamChannelUser -GroupId {team_id} -DisplayName "{channel_name}"{role_filter}',
			convert_json = True
		)

		# parse response
		# if channel not found, stop
		#note: 'Get-TeamChannelUser: Channel not found' isn't parseable json, so it craps out...
		if (type(response) == 'str' and response.find('Channel not found') != -1):
			return False
		else:
			# feed data into list
			member_list = {}

			for d in response:
				userid = d['User'].lower().replace('@ad.unsw.edu.au','')  # 'User ' = accountname@domain
				member_list[userid] = User(
					userid,     # zID
					d['Name'],  # name
					[],         # unknown class ids
					[]          # unknown groups
				)

			print(f'USER LIST for {channel_name}')
			for u in member_list:
				print(member_list[u])

			return member_list

	def add_users_to_channel (self, team_id, channel_name, users=[User], role='Member'):
		""" convenience function to add a list of users to a channel """
		for user in users:
			self.add_user_to_channel(team_id, channel_name, users[user], role)

	def add_user_to_channel (self, team_id, channel_name, user=User, role='Member'):
		""" add user to channel """
		response = self.process.run_command(
			f'Add-TeamChannelUser -GroupId {team_id} -DisplayName "{channel_name}" -User {user.id}@ad.unsw.edu.au'
		)

		# owners needs to be added as regular members first, then set to owner status
		if (response.find('User is not found in the team.') == -1 and role == 'Owner'):
			response = self.process.run_command(
				f'Add-TeamChannelUser -GroupId {team_id} -DisplayName "{channel_name}" -User {user.id}@ad.unsw.edu.au -Role {role}'
			)

		# parse response
		success = True
		if (response.find('User is not found in the team.') != -1 or response.find('Could not find member.') != -1):
			success = False
			self.log(f'Channel {channel_name}: Could not add {user} as {role}', 'ERROR')
		else:
			self.log(f'Channel {channel_name}: Added {user} as {role}')

		return success

	def remove_user_from_channel (self, team_id, channel_name, user=User, role='Member'):
		# remove from to relevant channel
		response = self.process.run_command(
			f'Remove-TeamChannelUser -GroupId {team_id} -DisplayName "{channel_name}" -User {user.id}@ad.unsw.edu.au'
		)

		success = True

		# by default, no response means things went fine
		if (len(response) != 0):
			print(response)

		# TODO parse response (as json will be easier)
		# Remove-TeamChannelUser: Error occurred while executing 
		# Code: NotFound
		# Message: Not Found
		# InnerError:
		# RequestId: 55982b3c-1319-4614-97bf-68e67ea94f90
		# DateTimeStamp: 2020-09-19T23:46:30
		# HttpStatusCode: NotFound
		

		self.log(f'Channel {channel_name}: Removed {user} as {role}')

		return success

	def update_channel (self, team_id, channel_name, desired_user_list, channel_user_list=None):
		self.log(f"Updating channel {channel_name} ({len(desired_user_list)} enrolments)")

		count_removed = 0
		count_added   = 0

		channel_user_list = channel_user_list
		if (channel_user_list is None):
			# get the team user list
			channel_user_list = self.get_channel_user_list(team_id, channel_name)

		# check current teams list against desired list
		#	remove any not on desired list (but check against whitelist, those are save from deletion)
		for user_in_teams_list in channel_user_list:
			if (user_in_teams_list not in desired_user_list and user_in_teams_list not in self.user_whitelist):
				response = self.remove_user_from_channel(team_id, channel_name, channel_user_list[user_in_teams_list])
				
				if (response):
					count_removed += 1
				
		# add any not in teams list but on desired list
		for user_in_desired_list in desired_user_list:
			if (user_in_desired_list not in channel_user_list):
				response = self.add_user_to_channel(team_id, channel_name, desired_user_list[user_in_desired_list])
				
				if (response):
					count_added += 1

		self.log(f'Updating channel {channel_name} complete (- {count_removed} / + {count_added})')

		return (count_removed, count_added)


	# TODO DEPRECATE
	def get_class_channels_user_list (self):
		""" iterate over each relevant Class ID and feed into existing data structure """
		for class_id in self.classes_list:
			self.get_class_channel_user_list(class_id)

	# TODO DEPRECATE
	def get_class_channel_user_list (self, class_id):
		cl = self.classes_list[class_id]

		cl['teams_user_list'] = self.get_channel_user_list(cl.teams_group_id, cl.name)

	# TODO DEPRECATE
	def create_class_channels (self, channel_type='Private', owners=[]):
		for class_id in self.classes_list:
			self.create_channel(team_id, channel_name, owners)

	# TODO DEPRECATE
	def add_user_to_all_class_channels (self, user=User, role='Member', course_list=[]):
		""" convenience function to add a single user to all channels at once """
		for class_id in self.classes_list:
			cl  = self.classes_list[class_id]

			# check if we exclude courses
			if (len(course_list) > 0 and cl.course not in course_list):
				continue  # skip this iteration and move on

			self.add_user_to_class_channel(cl.id, user, role)

	# TODO DEPRECATE
	def add_user_to_class_channel (self, class_id, user=User, role='Member'):
		""" # TODO deprecate this function """
		cl           = self.classes_list[str(class_id)]
		team_id      = cl['teams_group_id']
		channel_name = cl['name']

		return self.add_user_to_channel(team_id, channel_name, user, role)

	# TODO DEPRECATE
	def update_class_channels (self):
		total_count_removed = 0
		total_count_added   = 0

		for class_id in self.classes_list:
			(r, a) = self.update_class_channel(class_id)

			total_count_removed += r
			total_count_added   += a

		self.log(f'Updating all channels (totals: - {total_count_removed} / + {total_count_added})')

	def find_users (self, search_key, search_value, list_to_search=None, return_type='list'):
		""" convenience function to find users in a list """
		# TODO make it easier to access the default user lists
		list_to_search = list_to_search
		results        = []

		# default to master list
		if (list_to_search is None):
			list_to_search = self.user_list

		# check if list is actually a dict, and if so convert
		if (isinstance(list_to_search, dict)):
			list_to_search = list(list_to_search.values())

		for user in list_to_search:
			# check whether we match (part of) a string or other types of values
			if (isinstance(search_value, str)):
				if (search_key.lower() == 'group'):
					for group_name in user.groups:
						if (search_value in group_name):
							results.append(user)
				elif (search_key.lower() == 'group_exact'):
					for group_name in user.groups:
						if (search_value == group_name):
							results.append(user)
				elif (user[search_key].lower().find(search_value.lower()) != -1):
					results.append(user)
			else:
				if (search_key.lower() == 'class id'):
					if (search_value in user.class_ids):
						results.append(user)
				elif (user[search_key] == search_value):
					results.append(user)

		if (return_type == 'list'):
			return results
		else:
			results_dict = {}
			for result in results:
				results_dict[result.id] = result
			return results_dict
				
	def log (self, action='', type='INFO'):
		print(f'{type} - {action}')
		self.log_file.write(f'\n{datetime.now()} {type} - {action}')
		# ensure it is written rightaway to avoid loss of log data upon a crash
		self.log_file.flush()


class MoodleUpdater:
	"""
	Class that enables a small number of repetitive operations on Moodle

	Course id is unique, look at the url on Moodle to find the id for the course
	"""
	def __init__ (self, course_id, username, password):
		self.course_id = course_id
		self.csv_file  = None
		self.logged_in = False

		self.login(username, password)

	def login (self, username, password):
		"""
		Logs in to single-sign on for Moodle (thus with Office 365 credentials)
		usually doesn't fail, so that's quite nice
		"""
		print('INFO: Logging in to Moodle...')
		
		# use a custom profile to avoid download popup
		profile_preferences = {
			'browser.download.manager.showWhenStarting' : 'false',
			'browser.helperApps.alwaysAsk.force'        : 'false',
			'browser.download.folderList'               : 2,  # signals change away from default downloads folder
			'browser.download.dir'                      : os.getcwd(),
			'browser.helperApps.neverAsk.saveToDisk'    : 'text/csv, application/csv, text/html,application/xhtml+xml,application/xml, application/octet-stream, application/pdf, application/x-msexcel,application/excel,application/x-excel,application/excel,application/x-excel,application/excel, application/vnd.ms-excel,application/x-excel,application/x-msexcel,image/png,image/jpeg,text/html,text/plain,application/msword,application/xml,application/excel,text/x-c',
			'browser.download.manager.useWindow'        : 'false',
			'browser.helperApps.useWindow'              : 'false',
			'browser.helperApps.showAlertonComplete'    : 'false',
			'browser.helperApps.alertOnEXEOpen'         : 'false',
			'browser.download.manager.focusWhenStarting': 'false'
		}
		self.browser = Browser('firefox', profile_preferences=profile_preferences, headless=True)
		
		# login - will go to O365 authentication
		self.browser.visit('https://moodle.telt.unsw.edu.au/auth/oidc/')
		time.sleep(2)
		self.browser.fill('loginfmt', username)
		self.browser.find_by_id('idSIButton9').click()
		time.sleep(2)
		self.browser.fill('passwd', password)
		self.browser.find_by_id('idSIButton9').click()
		time.sleep(2)
		self.browser.find_by_id('idSIButton9').click()
		time.sleep(4)

		# check if we are now logged in
		if (self.browser.url.find('moodle.telt.unsw.edu.au') != -1):
			print('INFO: Logged in to Moodle successfully.')
			self.logged_in = True
			return True
		
		# else
		print('WARNING: Moodle login may have failed')
		# TODO handle this situation properly, we shouldn't continue
		return False

	def close (self):
		""" quit the browser so  it cleans up properly """
		self.browser.quit()

	def __enter__ (self):
		""" enables the use of the `with` statement """
		return self

	def __exit__ (self, type, value, traceback):
		""" so we can exit after using the `with` statement """
		self.close()

		if (traceback is None):  # no exception occured
			pass
		else:
			return False  # re-raise the exception to be transparent

	def get_users_csv (self):
		"""
		Downloads the user list as csv export from Moodle

		Note that Moodle sets the filename and this script's browser instance can't control that.
		It also doesn't indicate when a download may have completed, so this requires manual confirmation.
		"""
		print('INFO: Getting user data CSV file from Moodle...')
	
		# get all users on one page
		self.browser.visit(f'https://moodle.telt.unsw.edu.au/user/index.php?id={self.course_id}&perpage=5000&selectall=1')
		# give extra time to let large page settle
		time.sleep(30)
		# check if the 'select all' checkbox is ticked (should be per the url but fails with slow/large courses)
		checkbox_el    = self.browser.find_by_id('select-all-participants')
		checkbox_label = self.browser.find_by_css('label[for=select-all-participants]')
		# .text says 'Deselect all' if it's checked; 'Select all' if unchecked
		if (checkbox_label.text != 'Deselect all'):
			checkbox_el.click()  # select it now
			time.sleep(5)        # can be slow with 1000+ users

		# find the course name
		course_name = self.browser.find_by_tag('h1')[0].text
		filename    = course_name.lower().replace(' ','-').replace('&','-') + '.csv'

		# temporarily move the current file if it exists
		#   this prevents the new download to be renamed by the browser as file(1) to avoid overwriting it
		old_filename = filename.replace('.csv', '-old.csv')
		if (os.path.exists(filename)):
			os.rename(filename, old_filename)
		
		# select the export CSV option (which triggers a download)
		print('INFO: Downloading user list as CSV...')
		el = self.browser.find_by_id('formactionid')
		el.select('exportcsv.php')

		# it is assumed the file is now automatically downloaded to the current working folder
		#   however, there is no way of knowing the file has finished downloading
		#   so this needs some intervention...
		got_file = input('Downloaded file? [Y]es or [N]o: ').lower()

		if ('y' in got_file):
			print(f'INFO: Moodle user data downloaded to {filename}')

			# remove old file if it's there
			if (os.path.exists(old_filename)):
				os.remove(old_filename)

			self.csv_file = filename
			return filename
		else:
			# if unsuccessful we end up here...
			print(f'ERROR: Unable to download Moodle user data')

			# rename the old file to its former name
			if (os.path.exists(old_filename)):
				os.rename(old_filename, filename)

				return filename

	def get_grades_csv (self):
		""" TODO not sure if I ever used/tested this """
		print('INFO: Getting grades data CSV file from Moodle...')
		
		# go to grades download page (and just get all grades)
		self.browser.visit(f'https://moodle.telt.unsw.edu.au/grade/export/txt/index.php?id={self.course_id}')

		# click download button (name of input: 'submitbutton')
		self.browser.find_by_id('id_submitbutton').click()

		# TODO work out file download
		# filename example: 'DESN2000-5209_01060 Grades-20201022_0823-comma_separated.csv'

		# import os
		# import time
		# def tiny_file_rename(newname, folder_of_download):
		# 	filename = max([f for f in os.listdir(folder_of_download)], key=lambda xa :   os.path.getctime(os.path.join(folder_of_download,xa)))
		# 	if '.part' in filename:
			# 	time.sleep(1)
			# 	os.rename(os.path.join(folder_of_download, filename), os.path.join(folder_of_download, newname))
		# 	else:
			# 	os.rename(os.path.join(folder_of_download, filename),os.path.join(folder_of_download,newname))

		# import os
		# import shutil
		# filepath = 'c:\downloads'
		# filename = max([filepath +"\"+ f for f in os.listdir(filepath)], key=os.path.getctime)
		# shutil.move(os.path.join(dirpath,filename),newfilename)

	def auto_create_groups (self, group_by_type='classid', grouping_id=None):
		"""
		Automates the auto-creation interface on Moodle

		TODO `grouping_id` has to be fished out from the HTML, there might be a better way of setting that selection box
		(self.browser.select(selection_box_element, desired_option) is the way to go)
		"""
		print(f'INFO: Auto-creating groups by {group_by_type}...')
		
		# go straight to the auto-create groups page for the course
		self.browser.visit(f'https://moodle.telt.unsw.edu.au/group/autogroup.php?courseid={self.course_id}')
		
		# pick the grouping type
		group_type_el = self.browser.find_by_id('id_groupby')
		group_type_el.select( group_by_type.lower().replace(' ', '') )

		if (grouping_id is not None):
			# make the grouping selection area visible
			grouping_field_el  = self.browser.find_by_id('id_groupinghdr')
			grouping_header_el = grouping_field_el.first.find_by_tag('a')
			grouping_header_el.click()

			# select the pre-existing grouping id
			grouping_select_el = self.browser.find_by_id('id_grouping')
			grouping_select_el.select(grouping_id)  # e.g., the id 53183 may correspond to desired grouping id

		# submit the form
		self.browser.find_by_id('id_submitbutton').click()

		# give additional time to settle
		time.sleep(5)

		print('INFO: Auto-creating groups complete.')

	def add_gradebook_category (self, category_info={}):
		"""
		Ruin the gradebook by running this completely untested *ahem* experimental method
		"""
		# go straight to add/edit gradebook category page
		self.browser.visit(f'https://moodle.telt.unsw.edu.au/grade/edit/tree/category.php?courseid={self.course_id}')

		# expand all panes to simplify later steps
		expand_el = self.browser.find_by_css('a[class=collapseexpand]')
		expand_el.click()

		# set fields
		# category name
		if (category_info['name']):
			self.browser.find_by_css('input[id=id_fullname]').fill(category_info['name'])
		# aggregation method           
		if (category_info['aggregation']):
			aggr_el = self.browser.find_by_css('select[id=id_aggregation]')
			self.browser.select('id_aggregation', category_info['aggregation'])
		# ID number
		if (category_info['id']):
			self.browser.find_by_css('input[id=id_grade_item_idnumber]').fill(category_info['id'])
		# max grade
		if (category_info['grade_max']):
			self.browser.find_by_css('input[id=id_grade_item_grademax]').fill(category_info['grade_max'])
		# parent category
		if (category_info['parent_category']):
			self.browser.select('id_parentcategory', category_info['parent_category'])

		save_button_el = self.browser.find_by_id('id_submitbutton')
		save_button_el.click()

		# give some time to settle
		time.sleep(5)

		# new page will load, showing grade updates in progress
		# no need to click continue button as long as we know process completes (button appears then)
		continue_button_not_found = True

		while (continue_button_not_found):
			time.sleep(5)
			# TODO improve finding process to get this unique button
			continue_el = self.browser.find_by_css('button[type=submit]')

			if (continue_el == []):  # empty list means element is not found
				continue
			else:
				continue_button_not_found = False
				continue_el.click()

				# going back to gradebook now
				time.sleep(15)
				break

		# search for weight input field
		if (category_info['weight']):
			# first, find category_weight_id on the page
			# iterate over every relevant label and check the .text value for a match
			category_weight_id = None
			label_els          = self.browser.find_by_css('label[class=accesshide]')
			
			for l in label_els:
				if (l.text == f"Extra credit value for {category_info['name']}"):
					category_weight_id = label_el.get_attribute('for')
					break  # exit for loop
			
			if (category_weight_id is not None):
				weight_el = self.browser.find_by_css(f'input[id=weight_{category_weight_id}]')
				weight_el.fill(category_info['weight'])

				# submit changes
				self.browser.find_by_css('input[value=Save changes]').click()

				time.sleep(5)

	def add_section (self, section_info={}):
		""" Add a section to Moodle (note: completely untested) """

		# go to course main page and enable editing
		self.browser.visit(f'https://moodle.telt.unsw.edu.au/course/view.php?id={self.course_id}&notifyeditingon=1')

		# add an empty section
		self.browser.find_by_css('a[class=increase-sections]').click()
		# wait for page to reload
		time.sleep(10)

		# edit section
		# TODO find out section id (or pick last (new) section edit button)
		section_id = 0 #TODO
		self.browser.visit(f'https://moodle.telt.unsw.edu.au/course/editsection.php?id={section_id}&sr=0')
		time.sleep(10)

		# expand all

		# fill name
		#fill(section_info['name'])
		# fill description
		#fill(section_info['description'])
		
		# set access restrictions

		# save changes
		#TODO
		time.sleep(20)

	def add_project (self, project_info={}):
		""" convenience function that adds sections and gradebook categories for a project within the course """
		# TODO put in effort to enable me to be super-lazy next time :)
		pass


# -----------------------------------------------------------------------------


if __name__ == '__main__':
	"""
	This is a default use case
	Best practice is to create a new script file, import this one and make it work for your use case.
	"""
	login = LoginData()

	# with MoodleUpdater(54605, login.username, login.password) as mu:
	# 	my_path = mu.get_users_csv()

	# basic operation by default
	with TeamsUpdater(my_path, my_classes_list, my_user_whitelist) as tu:
		# connect at the start - everything else depends on this working
		tu.connect('automated', login.username, login.password)
		
		# import data first - later steps build on this
		tu.import_user_list()
		# tu.get_channels_user_list()

		# sync up channels - with many users, this takes a long time (approx 8 commands/minute)
		# tu.update_channels()
