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


# -----------------------------------------------------------------------------


@dataclass
class User:
	"""
	Class that holds user data
	"""
	id       : str
	name     : str
	class_ids: []
	groups   : []
	groupings: []
	email    : str  = ''
	owner    : bool = False  # 'Member'|'Owner'

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

	def in_grouping (self, grouping):
		return (grouping in self.groupings)


class LoginData:
	"""
	very basic class that safely stores login data (handy for repeated use).
	once login data is passed, there's no need to repeat it, thus no need
	to store passwords in any clear text file.
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

""" path to Moodle-exported CSV file (default given here, override with a suitable path) """
my_path = 'desn2000-engineering-design---professional-practice---2020-t3.csv'


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
	def __init__ (self, path=None, whitelist={}, process=None, username=None, password=None):
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

		# user ids that should not be touched as these are uni-managed service accounts
		self.exclusion_ids = ['svco365teamsmanage']

		# assign existing external process to connect to powershell
		#    creating a new one, if no process is provided, is deferred until necessary
		#    this significantly speeds up running the code as we can skip slow parts unless required
		self.process = process

		self.connected = False
		self.username  = username
		self.password  = password
	
	def __enter__ (self):
		""" enables the use of the `with` statement (as in `with TeamsUpdater() as tu:`) """
		return self

	def __exit__ (self, type, value, traceback):
		""" so we can exit after using the `with` statement """
		self.close()

		if (traceback is None):  # no exception occured
			pass
		else:
			return False  # re-raise the exception to be transparent

	def ensure_connected (self):
		"""
		Ensures we're connected to Teams backend whenever this method is called
		A call to this method should be added anywhere a process command is sent to the Teams backend.
		By only connecting when required, we skip the time-consuming login whenever possible.
		"""
		# first, ensure we have a working process
		if (self.process is None):
			self.process = PowerShellWrapper()

		# then, ensure the process is connected to Teams in the cloud
		if (self.connected == False):
			self.connected = self.process.connect_to_teams('automated', self.username, self.password)

		return self.connected
	
	def close (self):
		""" cleanup any open connections, files open """
		if (self.process is not None):
			self.process.close()
		self.log_file.close()

	def import_user_list (self):
		"""
		Imports a user list csv file that was exported from Moodle
		"""
		self.log(f'Importing data from: {self.data_path}')

		count_total       = 0
		count_instructors = 0
		count_students    = 0
		count_unknown     = 0

		groups_dict       = {}

		# before importing user data, get grouping data ready for later merging
		try:
			with open(self.data_path.replace('.csv', '_groupings.json'), 'r') as fg:
				groups_dict = json.loads( fg.read() )
		except FileNotFoundError as e:
			self.log(e, 'ERROR')
		
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

				# parse groups and groupings
				user_groups    = []
				user_groupings = []

				try:
					for n in range(1,100):
						g = user[f'Group{n}']
						# empty values are represented as float(nan) but we only care about strings anyway, so just test for that
						if (g is not None and type(g) is str and len(g) > 0):
							user_groups.append(g)

							# find groupings that incorporate this group
							if (g in groups_dict):
								for grouping in groups_dict[g]:
									if (grouping not in user_groupings):
										user_groupings.append(grouping)
				except KeyError:
					pass  # number of groups shown in Moodle export varies depending on number of groups in use

				# create User class from compiled info
				new_user = User(
					user_id,
					user['First name'] + ' ' + user['Surname'],
					class_ids,
					user_groups,
					user_groupings,
					user['Email address']
				)

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

					count_students += 1

		count_total = count_students + count_instructors + count_unknown
		self.log(f'Imported data on {count_total} users (students: {count_students}, instructors: {count_instructors}, unknown: {count_unknown}).\n\n')

	def export_student_list (self, project_list, tech_stream_list=None, replace_terms=None):
		""" Exports a list of students with project (and optional tech stream) information """

		# assume course code is first thing in path, for example: engg1000-title-2021-t1.csv
		course = self.data_path[:self.data_path.find('-')]
		
		output_path = self.data_path.replace('.csv', '-students.csv')

		with open(output_path, 'w') as f:
			# write out header
			header = 'Student zID,Student name,Email address,Class IDs,Course,Course coordinator,Course coordinator zID,Course coordinator email,Project,Project coordinator,Project coordinator zID,Project coordinator email,Project class,Project mentor,Project mentor zID,Project mentor email,Project team,Tech stream,Tech stream coordinator,Tech stream coordinator zID,Tech stream coordinator email,Tech stream mentor,Tech stream mentor zID,Tech stream mentor email'
			if (replace_terms != None):
				if (replace_terms['Project']):
					header = header.replace('Project',     replace_terms['Project'])
				if (replace_terms['Mentor']):
					header = header.replace('Mentor',      replace_terms['Mentor'])
					header = header.replace('mentor',      replace_terms['Mentor'].lower())
				if (replace_terms['Tech stream']):
					header = header.replace('Tech stream', replace_terms['Tech stream'])
			f.write(header)
			
			# iterate over all students in the list
			for sid in self.user_list:
				s = self.user_list[sid]

				# avoid including staff (who have no class ids) and partially unenrolled students (also no class ids)
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

				pclass          = '-'
				pteam           = '-'
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

				# loop over all groups to extract useful info
				for g in s.groups:

					# --- class ID-based matching below (fits most courses)
					
					if ( g.isdigit() ):
						# find the relevant project
						for pkey in project_list:
							p = project_list[pkey]
							
							# main_class_id may not exists for courses where it's irrelevant
							if ('main_class_id' in p and p['main_class_id'] == int(g)):
								project = pkey
								# if matching project is found, no need to continue the for loop trying other projects
								break
							elif ('classes' in p):
								for cl in p['classes']:
									if (cl['class_id'] == int(g)):
										if (cl['name'].find('LAB') != -1):
											tech_stream += f", {cl['name']}_{cl['class_id']}  [ {cl['description']} ]"
											
											# add demonstrator info
											for did in cl['demonstrators']:
												tmentor    += ', ' + self.user_whitelist[did].name
												tmentor_id += ', ' + did
												tmentor_em += ', ' + self.user_whitelist[did].email
											
											tech_stream = tech_stream.replace(    '-, ', '')
											tmentor     = tmentor.replace(   '-, ', '')
											tmentor_id  = tmentor_id.replace('-, ', '')
											tmentor_em  = tmentor_em.replace('-, ', '')
										else:
											pclass += f", {cl['name']}_{cl['class_id']}  [ {cl['description']} ]"
											
											# add demonstrator info
											for did in cl['demonstrators']:
												pmentor    += ', ' + self.user_whitelist[did].name
												pmentor_id += ', ' + did
												pmentor_em += ', ' + self.user_whitelist[did].email
											
											pclass     = pclass.replace(    '-, ', '')
											pmentor    = pmentor.replace(   '-, ', '')
											pmentor_id = pmentor_id.replace('-, ', '')
											pmentor_em = pmentor_em.replace('-, ', '')

					# --- group name based matching below (fits ENGG1000 best)

					# TODO generalise to allow other terms than 'Project'
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

					if (g.lower().find('team') != -1):
						pteam = g.replace('Project ','')

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
				
				# --- below we assume project and streams have been found
				#     now, it's about filling in the details

				if (project != '-'):
					pcoordinator_id = project_list[project]['coordinators']
					
					for index, pid in enumerate(pcoordinator_id):
						# if user is in list but not on Moodle, it may not be in whitelist yet
						if (pid in self.user_whitelist):
							pcoordinator    += ', ' + self.user_whitelist[pid].name
							pcoordinator_em += ', ' + self.user_whitelist[pid].email

							if (index == 0):
								pcoordinator    = pcoordinator.replace('-, ','')
								pcoordinator_em = pcoordinator_em.replace('-, ','')

				if (tech_stream_list is not None and tech_stream != '-'):
					tcoordinator_id = tech_stream_list[tech_stream]['coordinators']
					
					for index, tid in enumerate(tcoordinator_id):
						# if user is in list but not on Moodle, it may not be in whitelist yet
						if (pid in self.user_whitelist):
							tcoordinator    += ', ' + self.user_whitelist[tid].name
							tcoordinator_em += ', ' + self.user_whitelist[tid].email

							if (index == 0):
								tcoordinator    = tcoordinator.replace('-, ','')
								tcoordinator_em = tcoordinator_em.replace('-, ','')

				# --- finally, write output for this student
				f.write(f'\n{s.id},{s.name},{s.email},"{",".join(map(str,s.class_ids))}",{course},"{ccoordinator}","{ccoordinator_id}","{ccoordinator_em}",{project},"{pcoordinator}","{", ".join(pcoordinator_id)}","{pcoordinator_em}","{pclass}","{pmentor}","{pmentor_id}","{pmentor_em}","{pteam}","{tech_stream}","{tcoordinator}","{", ".join(tcoordinator_id)}","{tcoordinator_em}","{tmentor}","{tmentor_id}","{tmentor_em}"')

			self.log(f'Exported student list to {output_path}\n\n')


	def create_team (self, name, description='', visibility='Private', owners=[], template=None, info=''):
		"""
		Create a new Team. Connected account will become an owner automatically.

		see: https://docs.microsoft.com/en-us/powershell/module/teams/new-team?view=teams-ps
		info parameter isn't used/required for anything but may be useful to parse the logs and keep team data and other info together.

		  template : (optional) String, either "EDU_Class" or "EDU_PLC"
		"""
		self.ensure_connected()

		template_param = ''
		if (template is not None):
			template_param = f' -Template {template}'
		
		# TODO improve this by using convert_json = True to get team object in one go
		# create team
		response = self.process.run_command(
			f'$group = New-Team -DisplayName "{name}" -Description "{description}" -Visibility {visibility}{template_param}'
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
		self.ensure_connected()

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
			user_list = self._parse_response_users(response, team_id, print_users=True)

			return user_list

	def _parse_response_users (self, response_data, set_name, print_users=False):
		""" internal method for parsing Teams json.parsed response data """
		user_list     = {}
		response_data = response_data

		# single user isn't given as a list, just the user dict, so wrap in list
		if (isinstance(response_data, dict)):
			response_data = [response_data]

		for d in response_data:
			userid = d['User'].lower().replace('@ad.unsw.edu.au','')  # 'User ' = accountname@domain
			user_list[userid] = User(
				userid,     # zID
				d['Name'],  # name       
				[],         # unknown class ids
				[],         # unknown groups
				[],         # unknown groupings
				d['User']
				# TODO include role data?
			)

		if (print_users):
			print(f'USER LIST for {set_name}')
			for k in user_list:
				print(user_list[k])

		return user_list 

	def remove_users_from_team (self, team_id, users=[User], role='Member'):
		""" coonvenience function to remove a list of users in one go """
		for u in users:
			self.remove_user_from_team(team_id, u, role)

	def remove_user_from_team (self, team_id, user=User, role='Member'):
		""" removing a user as role='Owner' keeps them as a team member """
		self.ensure_connected()

		# skip the uni-added service accounts
		if (user.id in self.exclusion_ids):
			return False

		response = self.process.run_command(
			f'Remove-TeamUser -GroupId {team_id} -User {user.id}@ad.unsw.edu.au -Role {role}'
		)

		self.log(f'Team {team_id}: Removed {user} as {role}')

		# TODO check response
		#Remove-TeamUser: Error occurred while executing 
		#Remove-TeamUser: Last owner cannot be removed from the team
		return True

	def add_users_to_team (self, team_id, users=[User], role='Member'):
		""" coonvenience function to add a list of users in one go """
		for user in users:
			self.add_user_to_team(team_id, user, role)

	def add_user_to_team (self, team_id, user=User, role='Member'):
		""" Adds a user to the team. Add an existing member as an `Owner` to elevate their role. """
		self.ensure_connected()

		# skip the uni-added service accounts
		if (user.id in self.exclusion_ids):
			return False

		response = self.process.run_command(
			f'Add-TeamUser -GroupId {team_id} -User {user.id}@ad.unsw.edu.au -Role {role}'
		)

		self.log(f'Team {team_id}: Added {user} as {role}')

		# TODO check response
		return True

	def update_team (self, team_id, desired_user_list, team_user_list=None, role='All'):
		""" add/remove users to match the `desired_user_list` """
		self.ensure_connected()

		count_removed = 0
		count_added   = 0

		desired_user_list = self.ensure_dict(desired_user_list)
		team_user_list    = self.ensure_dict(team_user_list)

		if (team_user_list is None):
			# get the team user list
			team_user_list = self.get_team_user_list(team_id, role)

		# check current teams list against desired list
		#	remove any not on desired list
		for user_in_teams_list in team_user_list:
			# skip the uni-added service accounts
			if (user_in_teams_list in self.exclusion_ids): 
				continue

			if (user_in_teams_list not in desired_user_list):
				# no role is indicated, so removal should remove the user rather than demote them from owner to member
				response = self.remove_user_from_team(team_id, team_user_list[user_in_teams_list])
				
				if (response):
					count_removed += 1
				
		# add any not in teams list but on desired list
		for user_in_desired_list in desired_user_list:
			if (user_in_desired_list not in team_user_list):
				if (role == 'All'):
					# follow User role
					response = self.add_user_to_team(team_id, desired_user_list[user_in_desired_list], role=desired_user_list[user_in_desired_list].role())
				else:
					# follow the generic role indicated
					response = self.add_user_to_team(team_id, desired_user_list[user_in_desired_list], role)
				
				if (response):
					count_added += 1

		self.log(f'Updating team {team_id} complete (- {count_removed} / + {count_added})')

		return (count_removed, count_added)

	def create_channel (self, team_id, channel_name, channel_type='Standard', description=None):
		""" Create a new channel in a team with the specific name and type """
		self.ensure_connected()

		desc = ''
		if (description != None):
			desc = f' -Description "{description}"'

		# create channel
		response = self.process.run_command(
			f'New-TeamChannel -GroupId {team_id} -DisplayName "{channel_name}" -MembershipType {channel_type}{desc}',
			convert_json = True
		)

		# TODO parse response
		# if (response.find(''))
		#New-TeamChannel: Error occurred while executing 
		#Code: BadRequest
		#Message: Channel name already existed, please use other name.

		self.log(f'Created channel {channel_name} in Team {team_id}')

	def set_channel (self, team_id, channel_name, new_channel_name=None, description=None):
		""" adjust name and description of an existing channel """
		self.ensure_connected()

		# only continue if there is something to adjust
		if (new_channel_name is None and description is None):
			return False

		new_name = ''
		if (new_channel_name != None):
			new_name = f' -NewDisplayName "{new_channel_name}"'

		desc = ''
		if (description != None):
			desc = f' -Description "{description}"'

		# edit channel
		response = self.process.run_command(
			f'Set-TeamChannel -GroupId {team_id} -CurrentDisplayName "{channel_name}" {new_name}{desc}'
		)

		# TODO parse response
		#Set-TeamChannel: Channel not found

		self.log(f'Edited channel {channel_name} in Team {team_id}')

	def get_channels_user_list (self, channels_list, role='All'):
		""" TODO untested and unused at the moment """
		channels_user_lists = {}
		for ch in channels_list:
			channels_user_lists[ch.name] = self.get_channel_user_list(ch.team_id, ch.name, role=role)
		return channels_user_lists

	def get_channel_user_list (self, team_id, channel_name, role='All'):
		""" Get list of current users in channel, and return a dict with user ids as the keys """
		self.ensure_connected()

		print(team_id, channel_name, role)

		# add filter if required
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
			member_list = self._parse_response_users(response, channel_name, print_users=True)

			return member_list

	def add_users_to_channel (self, team_id, channel_name, users=[User], role='Member'):
		""" convenience function to add a list of users to a channel """
		for user in users:
			self.add_user_to_channel(team_id, channel_name, user, role)

	def add_user_to_channel (self, team_id, channel_name, user=User, role='Member'):
		""" add user to channel """
		self.ensure_connected()

		# skip the uni-added service accounts
		if (user.id in self.exclusion_ids):
			return False

		response = self.process.run_command(
			f'Add-TeamChannelUser -GroupId {team_id} -DisplayName "{channel_name}" -User {user.id}@ad.unsw.edu.au'
		)

		# owners need to be added as regular members first, then once more to set the owner status
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
		""" remove user from specified channel """
		self.ensure_connected()

		# skip the uni-added service accounts
		if (user.id in self.exclusion_ids):
			return False

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

	def update_channel (self, team_id, channel_name, desired_user_list, channel_user_list=None, role='All'):
		self.log(f"Updating channel {channel_name} ({len(desired_user_list)} enrolments)")

		count_removed = 0
		count_added   = 0

		desired_user_list = self.ensure_dict(desired_user_list)
		channel_user_list = self.ensure_dict(channel_user_list)

		if (channel_user_list is None):
			# get the team user list
			channel_user_list = self.get_channel_user_list(team_id, channel_name, role)

		# check current teams list against desired list
		#	remove any not on desired list (but check against whitelist, those are save from deletion)
		for user_in_teams_list in channel_user_list:
			# skip the uni-added service accounts
			if (user_in_teams_list in self.exclusion_ids): 
				continue

			if (user_in_teams_list not in desired_user_list and user_in_teams_list not in self.user_whitelist):
				# no role is indicated, so removal should remove the user rather than demote them from owner to member
				response = self.remove_user_from_channel(team_id, channel_name, channel_user_list[user_in_teams_list])
				
				if (response):
					count_removed += 1
				
		# add any not in teams list but on desired list
		for user_in_desired_list in desired_user_list:
			if (user_in_desired_list not in channel_user_list):
				# TODO manage role
				response = self.add_user_to_channel(team_id, channel_name, desired_user_list[user_in_desired_list])

				if (role == 'All'):
					# follow User role
					response = self.add_user_to_channel(team_id, channel_name, desired_user_list[user_in_desired_list], role=desired_user_list[user_in_desired_list].role())
				else:
					# follow the generic role indicated
					response = self.add_user_to_channel(team_id, channel_name, desired_user_list[user_in_desired_list], role)
				
				if (response):
					count_added += 1

		self.log(f'Updating channel {channel_name} complete (- {count_removed} / + {count_added})')

		return (count_removed, count_added)

	def find_users (self, search_key, search_value, list_to_search=None, return_type='list'):
		""" convenience function to find users in a list """
		# TODO make it easier to access the default user lists
		list_to_search = list_to_search
		results        = []

		# default to master list
		if (list_to_search is None):
			list_to_search = self.user_list

		# check if list is actually a dict, and if so convert
		list_to_search = self.ensure_list(list_to_search)

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
				elif (search_key.lower() == 'grouping'):
					for grouping_name in user.groupings:
						if (search_value in grouping_name):
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
				
	def ensure_list (self, input_list):
		""" if input is actually a dict, convert to a list and return """
		if (input_list is None):
			return None

		if (isinstance(input_list, dict)):
			return list(input_list.values())
		else:
			return input_list

	def ensure_dict (self, input_dict):
		""" if input is actually a list, convert to a dict and return """
		if (input_dict is None):
			return None
		
		if (isinstance(input_dict, list)):
			d = {}
			for index, li in enumerate(input_dict):
				if (li.id):
					d[li.id] = li
				else:
					d[index] = li
			return d
		else:
			return input_dict

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

	def get_grouping_data (self, output_path):
		""" TODO extracts grouping info and exports to csv """
		print('INFO: Getting grouping data from Moodle...')
		
		# go to grouping overview page
		self.browser.visit(f'https://moodle.telt.unsw.edu.au/group/groupings.php?id={self.course_id}')

		time.sleep(5)

		# structure of the groupings table
		#<table class="generaltable">  <-- class occurs only once so it's unique
		#	<thead>
		#	<tbody>
		#		<tr>
		#			<td class=cell c0>grouping name</td>
		#			<td class=cell c1>group1, group2</td>

		# find the table
		table = self.browser.find_by_css('table[class=generaltable]').first
		
		# within .generaltable, get all elements with class 'cell c0' and 'cell c1'
		grouping_list_els = table.find_by_xpath(".//td[@class='cell c0']")
		groups_list_els   = table.find_by_xpath(".//td[@class='cell c1']")

		# take element lists and extract inner text from elements
		grouping_list = []
		groups_list   = []

		# c0 is list of grouping names
		for g in grouping_list_els:
			grouping_list.append( g.text )

		# c1 is list of group names for a grouping --> c1.split(', ')
		for g in groups_list_els:
			groups_list.append( g.text.split(', ') )

		# with all data available, transform into useful format
		#    groups_dict will hold all groups encountered, and for each list the groupings it's part of
		#    elsewhere, this can be used to add grouping info based on the groups encountered
		groups_dict = {}

		for index in range(0,len(grouping_list)):
			grouping = grouping_list[index]
			groups   = groups_list[index]

			for group in groups:
				# add grouping to the group's list, or create a fresh list
				if (group in groups_dict):
					if (grouping not in groups_dict[group]):
						groups_dict[group].append(grouping)
				else:
					groups_dict[group] = [grouping]

		# export data to file
		with open(output_path.replace('.csv', '_groupings.json'), 'w') as f:
			f.write( json.dumps(groups_dict, sort_keys=True, indent=4) )

		print('INFO: Grouping data export complete.')

		return groups_dict

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

	def auto_create_groups (self, group_by_type='classid', grouping_name=None):
		""" Automates the groups auto-creation interface on Moodle """
		print(f'INFO: Auto-creating groups by {group_by_type}...')
		
		# go straight to the auto-create groups page for the course
		self.browser.visit(f'https://moodle.telt.unsw.edu.au/group/autogroup.php?courseid={self.course_id}')
		
		# pick the grouping type
		group_type_el = self.browser.find_by_id('id_groupby')
		group_type_el.select( group_by_type.lower().replace(' ', '') )

		if (grouping_name is not None):
			# make the grouping selection area visible
			grouping_field_el  = self.browser.find_by_id('id_groupinghdr')
			grouping_header_el = grouping_field_el.first.find_by_tag('a')
			grouping_header_el.click()

			# select the option (make sure to pick the last one as it may occur more than once elsewhere on the page)
			# grouping_select_el = self.browser.find_by_id('id_grouping')
			self.browser.find_option_by_text( grouping_name ).last.click()
			# alt method: self.browser.select(selection_box_element, desired_option)

		# submit the form
		self.browser.find_by_id('id_submitbutton').click()

		# give additional time to settle
		time.sleep(5)

		print('INFO: Auto-creating groups complete.')

	def add_gradebook_category (self, category_info={}):
		"""
		Ruin the gradebook by running this experimental method

		category_info is a dict {} with the following parameters:
		  name            : (required) String of text
		  aggregation     : (optional) String of text, must match option name in Moodle
		  id              : (optional) String of text
		  grade_max       : (optional) Number (can be int or float)
		  parent_category : (optional) String of text, must match existing category name
		  weight          : (optional) Float in range [0,1]
		"""
		print(f'INFO: Adding the {category_info["name"]} gradebook category...')

		# go straight to add/edit gradebook category page
		self.browser.visit(f'https://moodle.telt.unsw.edu.au/grade/edit/tree/category.php?courseid={self.course_id}')

		# give some time to settle
		time.sleep(10)

		# expand all panes to simplify later steps
		expand_el = self.browser.find_by_css('a[class=collapseexpand]')
		expand_el.click()

		# set fields
		# category name
		if ('name' in category_info):
			self.browser.find_by_css('input[id=id_fullname]').fill(category_info['name'])
		# aggregation method           
		if (category_info['aggregation']):
			self.browser.find_option_by_text( category_info['aggregation'] ).first.click()
		# ID number
		if ('id' in category_info):
			self.browser.find_by_css('input[id=id_grade_item_idnumber]').fill(category_info['id'])
		# max grade
		if ('grade_max' in category_info):
			self.browser.find_by_css('input[id=id_grade_item_grademax]').fill(str(category_info['grade_max']))
		# parent category
		if ('parent_category' in category_info):
			self.browser.find_option_by_text( category_info['parent_category'] ).first.click()

		save_button_el = self.browser.find_by_id('id_submitbutton')
		save_button_el.click()

		# give some time to settle
		time.sleep(10)

		# new page will load, showing grade updates in progress
		# no need to click continue button as long as we know process completes (button appears then)
		# TODO this intermediate page doesn't show when no grades are present, so must be skipped then
		if (False):
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
		if ('weight' in category_info):
			# first, find category_weight_id on the page
			# iterate over every relevant label and check the .text value for a match
			category_weight_id = None
			label_els          = self.browser.find_by_css('label[class=accesshide]')
			
			for l in label_els:
				if (l.text == f"Extra credit value for {category_info['name']}"):
					category_weight_id = l['for']
					break  # found the right one, exit for loop early
			
			if (category_weight_id is not None):
				weight_el = self.browser.find_by_css(f'input[id={category_weight_id}]')
				weight_el.fill(str(category_info['weight']))

				# submit changes
				self.browser.find_by_css('input[value=Save\ changes]').click()

				time.sleep(5)

		print(f'INFO: Added the {category_info["name"]} gradebook category.')

	def add_section (self, section_info={}):
		"""
		Add a section to Moodle

		section_info is a dict {} with the following parameters:
		  name         : (required) String of text
		  description  : (optional) String of text
		  restrictions : (optional) list of dicts, e.g. [{'group': 'some group'}, {'grouping': 'some grouping'}]
		  hidden       : (optional) True or False
		"""
		print(f'INFO: Adding section named {section_info["name"]}...')

		# go to course main page 
		self.browser.visit(f'https://moodle.telt.unsw.edu.au/course/view.php?id={self.course_id}')

		time.sleep(10)

		# first check if section already exists
		section_title_els = self.browser.find_by_css('a.quickeditlink')
		for s_title in section_title_els:
			if (s_title == section_info['name']):
				print(f'INFO: Section named {section_info["name"]} already exists. Skipped.')
				return

		# enable editing by clicking the right button
		buttons = self.browser.find_by_css('button[type=submit]')
		for b in buttons:
			if (b.text == 'Turn editing on'):
				b.click()

				# let things settle
				time.sleep(15)
				
				break  # no need anymore to check other buttons
			elif (b.text == 'Turn editing off'):
				break  # we're in the editing mode already

		# add an empty section
		self.browser.find_by_css('a[class=increase-sections]').click()
		# wait for page to reload
		time.sleep(10)

		# edit section
		section    = self.browser.find_by_css('li.section').last
		section_id = section['aria-labelledby'].replace('sectionid-', '').replace('-title', '')
		self.browser.visit(f'https://moodle.telt.unsw.edu.au/course/editsection.php?id={section_id}&sr=0')
		
		time.sleep(10)

		# expand all panes to simplify later steps
		expand_el = self.browser.find_by_css('a[class=collapseexpand]')
		expand_el.click()

		# fill name
		if ('name' in section_info):
			# enable a custom name
			self.browser.find_by_id('id_name_customize').click()

			self.browser.find_by_id('id_name_value').fill(section_info['name'])
		# fill description
		if ('description' in section_info):
			self.browser.find_by_id('id_summary_editor').fill(section_info['description'])
		
		# set access restrictions
		if ('restrictions' in section_info):
			for r in section_info['restrictions']:
				self.browser.find_by_text('Add restriction...').click()
				time.sleep(1)

				if ('group' in r):
					self.browser.find_by_id('availability_addrestriction_group').click()
					time.sleep(1)
					self.browser.find_option_by_text(r['group']).first.click()
				elif ('grouping' in r):
					self.browser.find_by_id('availability_addrestriction_grouping').click()
					time.sleep(1)
					self.browser.find_option_by_text(r['grouping']).first.click()
				else:
					print(f'WARNING restriction type in {r} is not supported yet')
				time.sleep(1)

				# toggle 'hide otherwise' eye icon when desired (do so by default)
				availability_eye_el = self.browser.find_by_css('a.availability-eye')
				availability_eye_el.last.click()

		# save changes
		self.browser.find_by_id('id_submitbutton').click()

		# returning to main sectin view
		time.sleep(10)

		# set hidden state (must be done from section view)
		if ('hidden' in section_info and section_info['hidden'] == True):
			# first, toggle the edit popup to be visible, then click the hide button within
			edit_toggle_buttons = self.browser.find_by_css('a.dropdown-toggle')
			edit_toggle_buttons.last.click()
			time.sleep(0.5)

			hide_section_button = self.browser.find_by_text('Hide section')
			hide_section_button.last.click()
			time.sleep(5)

		print(f'INFO: Added section named {section_info["name"]}.')

	def export_default_groups_list (self, project_list):
		""" Generates a csv file for importing into Moodle with basic group and grouping setup """
		
		output_path = self.csv_file.replace('.csv', '-groups.csv')

		with open(output_path, 'w') as fo:
			# write header
			fo.write('groupname,groupingname')

			for pname in project_list:
				p = project_list[pname]

				fo.write(f'\n"Staff {pname}","Staff Grouping (All)"')

				# TODO make this more accurate and/or flexible
				# ENGG1000 would use 'Project Group - {pname}' and usually not 'Project Grouping - {pname}'
				# ^ it isn't dependent on class ids like DESN2000 is
				# use something else instead of 'Students'?
				if ('main_class_id' in p):
					fo.write(f'\n"{p["main_class_id"]}","Students Grouping - {pname}"')
					fo.write(f'\n"{p["main_class_id"]}","Students Grouping (All)"')
				else:
					fo.write(f'\n"DUMMY GROUP","Students Grouping - {pname}"')
					fo.write(f'\n"DUMMY GROUP","Students Grouping (All)"')
				
				fo.write(f'\n"DUMMY GROUP","Student Teams - {pname}"')
				fo.write(f'\n"DUMMY GROUP","Student Teams (All)"')

			print(f'\nExported groups list to {output_path}\n\n')


class LMUpdater:
	"""
	Class that enables a small number of repetitive operations on the Learning Management system via myUNSW
	"""
	def __init__ (self, course_name, course_term, username, password):
		self.course_name = course_name
		self.course_term = course_term
		self.logged_in = False

		self.login(username, password)

	def login (self, username, password):
		"""
		Logs in to single-sign on for myUNSW (thus with Office 365 credentials)
		usually doesn't fail, so that's quite nice
		"""
		print('INFO: Logging in to Learning Management on myUNSW...')

	def close (self):
		""" quit the browser so  it cleans up properly """
		pass
		# self.browser.quit()

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

	def update_staff_list (self, staff_list):
		"""
		Update staff members

		staff_list is a set of dicts {} with the following parameters:
		  id           : (required) String with unique username
		  role         : (required) String, one of Instructor|Grading Tutor|Non-Grading Tutor|Teaching Assistant|Blind Marker|Staff Auditor
		  name         : (optional) String of text
		"""

		#self.browser.visit('https://my.unsw.edu.au/academic/learningManagement/lmsModuleSearch.xml')
		#select name 'termSrch', select value '5216' for '5216 Term 2 2021'
		#input name 'includedCourseSrch', fill to self.course_name
		#input submit 'bsdsSubmit-search'
		# time.sleep(5)
		#click on input submit 'bsdsSubmit-select-1' (assuming we have one hit)
		# will direct us to 'https://my.unsw.edu.au/academic/learningManagement/lmsModuleCourses.xml'
		# time.sleep(5)

		# go to staff page
		# self.browser.visit('https://my.unsw.edu.au/academic/learningManagement/lmsStaffRoles.xml')

		# parse table
		staff_on_lm = {}
		# for each tr with class 'data', extract td with class 'data', gives: staff zIDs, name, role (select with name 'role-0')
		# staff_on_lm[zID] = {}

		#for staff_on_lm but not in staff_list
		# remove with input submit 'bsdsSubmit-deleteStaff0'

		# for staff_list and staff_on_lm
		# adjust role if it's not matching
		
		#for staff_list but not in staff_on_lm
		# add by searching zID
		# fill input text 'staffId' with staff['id'].replace('z','')
		# click input submit 'bsdsSubmit-searchID'
		#time.sleep(5)
		# pick from list of names found (id is unique, so list should be one)
		# iterate until found
		# click to add
		#time.sleep(5)
		# set their role here, or let it be set in step 2 if we loop there?

		# when done, save and submit
		


# -----------------------------------------------------------------------------


if __name__ == '__main__':
	"""
	This is a default use case
	Best practice is to create a new script file, import this script's classes there, and make it work for your use case.
	"""
	# get login info
	login = LoginData()

	# get data from Moodle
	moodle_course_id = 54605

	with MoodleUpdater(moodle_course_id, login.username, login.password) as mu:
		my_path = mu.get_users_csv()

	# basic operation by default
	with TeamsUpdater(my_path, my_user_whitelist, username=login.username, password=login.password) as tu:
		# import data first - later steps build on this
		tu.import_user_list()
		
		# do other things
