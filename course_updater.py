#!/usr/bin/python3

#####
# script requires python version 3.7+ and powershell 7+ to be installed
# only tested on MacOS 10.15
#
# generally, this script is as resilient as a toddler with icecream in their hand
# it will drop and create a scene at some stage...
#####

from dataclasses import dataclass, field
# from typing import Dict

import pandas
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


# it it assumed Teams are already created and that students are auto-added to teams
#	this script is only concerned with keeping private channels in sync with the Moodle list

# make sure that for each tutorial-like ClassItem, there is a corresponding private channel
#	could be done programmatically but channel name is likely hard to form without knowledge of timetable.
#   timetable info can be fed in from classutil website but needs parsing.
#   setting them up manually is very likely to be faster (including adding demonstrators, etc).
#	generating the list below isn't too time intensive using regex on the classutil list.

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
	id    : str
	name  : str
	owner : bool = False  # 'Member'|'Owner'
	course: str  = ''

	def __getitem__ (self, key):
		return getattr(self, key)

	def __str__ (self):
		return f'{self.name} ({self.id})'

	def role (self):
		return ('Member', 'Owner')[self.owner]


# very basic class that stores login data (handy for repeated use)
class LoginData:
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
# default input variables

# Moodle-exported CSV file
my_path = 'desn2000-engineering-design---professional-practice---2020-t3.csv'

# have a list of classes (see for structure the ClassItem class below)
my_classes_list = [
	ClassItem(1112,  'Demonstrators',  '458b02e9-dea0-4f74-8e09-93e95f93b473', 'DESN2000_2020T3_CVEN'),
]

# have a whitelist of users not to be removed from channels (demonstrators, etc)
#	these users typically will not feature in Moodle-based ClassID lists
#	although such a whitelist is also generated/expanded from staff listed in Moodle
my_user_whitelist = []


# -----------------------------------------------------------------------------


###
# this is what happens when you know python and think you'll just call
# some powershell commands, only to realise when you're in knee-deep that
# the login step requires the shell process to stay alive between calls
# and now you have to tame powershell somehow, making you wonder if simply
# learning powershell in the first place wouldn't have been a better bet
#
# handles powershell commands in the background, works kind of like the
# pexpect library, only returning when it encounters the reappearing prompt
# or another string in the output that we want to stop at.
#
# very simple, very likely to not work with most edge cases
###
class PowerShellWrapper:
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
			return False  # re-raise the exception to be transparent

	def close (self):
		# disconnect and confirm any prompts that may come our way
		if (self.connected_to_teams):
			self.run_command('Disconnect-MicrosoftTeams')

		self.process.stdin.close()
		self.process.kill()

		if (self.debug_mode):
			self.log.close()

	def run_command (self, command, do_run=True, delay=0.5, return_if_found=None, convert_json=False):
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
			output = json.loads(output)

		self.latest_output = output

		# log command and output data for debugging purposes
		if (self.debug_mode):
			with open(f'cmd_logs/cmd_{self.count}.txt','w') as f:
				f.write(f'COMMAND: {command}\n\n')
				f.write(str(output))   # making sure this is always a string

		return output

	def connect_to_teams (self, login_method='popup', username=None, password=None):
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
					# note: this procedure doesn't work because basic authentication doesn't support the right sign-on protocols
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


###
# Wrapper around powershell teams commands, with additional logic to help with
# generating channels and keeping users in sync with an external file.
###
class TeamsUpdater:
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
		# not optimal from a memory/neatness point of view but it's the lazy approach and works fine
		self.user_whitelist  = {}
		for name in whitelist:
			self.user_whitelist[str(name.id)] = name

		# idem, a dict not a list
		self.classes_list    = {}
		for cl in classes:
			self.classes_list[str(cl.id)] = cl

		# use external process to connect to powershell or create new one
		if (process is not None):
			self.process = process
		else:
			self.process = PowerShellWrapper()
	
	# so we can use the with statement
	def __enter__ (self):
		return self

	# so we can exit after using the with statement
	def __exit__ (self, type, value, traceback):
		self.close()

		if (traceback is None):  # no exception occured
			pass
		else:
			return False  # re-raise the exception to be transparent
	
	def connect (self, login_method='default', username=None, password=None):
		# get connected early -> this way later commands that require a connection won't fail
		self.connected = self.process.connect_to_teams(login_method=login_method, username=username, password=password)

	def close (self):
		# cleanup any open connections, files open
		if (self.process is not None):
			self.process.close()
		self.log_file.close()

	def get_all_data (self):
		self.import_user_list()
		self.get_class_channels_user_list()

	def import_user_list (self):
		self.log(f'Importing data from: {self.data_path}')

		unknown_class_ids = []

		count_instructors = 0
		count_students    = 0
		count_unknown     = 0
		
		# open and read CSV file - assumes existence of columns named Username (for zID), First Name, Surname
		dataframe = pandas.read_csv(self.data_path)
		
		# for every user, add them to the known class lists
		#	when complete, this gives a complete view of users in each class
		for index, user in dataframe.iterrows():
			user_id = user['Username'].lower()  # make sure it's all lowercase, for later comparisons

			new_user = User(
				user_id,
				user['First name'] + ' ' + user['Surname']
			)

			# users without classes assigned get added to the whitelist
			# in Moodle, more or less by definition, no ClassID -> staff
			if (user['Class ID'] == '-'):
				# do another check to make sure this user is actually staff
				#   adding a user to this group requires manual assignment in Moodle
				#   as an alternative, you can add them into the user whitelist passed in at the start
				if (isinstance(user['Group1'], str) and user['Group1'].lower().find('staff') != -1):
					new_user.owner = True

					# don't overwrite prior whitelist user data
					if (user_id not in self.user_whitelist.keys()):
						self.user_whitelist[user_id] = new_user

					count_instructors += 1
				else:
					self.log(f'User {new_user} has no Class IDs but is not a staff member: skipped.', 'WARNING')
					count_unknown += 1
			else:
				# field is comma-separated, so undo this first
				class_ids = user['Class ID'].split(',')

				# now, iterate over the found class IDs and add the user to its list
				for class_id in class_ids:
					if (class_id in self.classes_list.keys()):
						# overwrite, likely 
						self.classes_list[class_id]['desired_user_list'][user_id] = new_user
					else:
						# add class_id to list of unknown classes - useful feedback in case a class is missing by accident
						if (class_id not in unknown_class_ids):
							unknown_class_ids.append(class_id)
						else:
							pass  # ignore any later encounters

				count_students += 1

		# sort the unknown class ids from low to high (requires intermediate conversion to int)
		unknown_class_ids = list(map(int, unknown_class_ids))
		unknown_class_ids.sort()
		unknown_class_ids = list(map(str, unknown_class_ids))
		self.log(f'No class items that match Class IDs {", ".join(unknown_class_ids)}')

		self.log(f'Imported data on {len(dataframe.index)} users (students: {count_students}, instructors: {count_instructors}, unknown: {count_unknown}).\n\n')

	# TODO work out return format (just a list isn't very useful? needs channel name at least)
	# def get_channels_user_list (self, channels_list):
	# 	for ch in channels_list:
	# 		self.get_single_channel_user_list(ch.team_id, ch.name)

	def get_class_channels_user_list (self):
		# iterate over each relevant Class ID
		for class_id in self.classes_list:
			self.get_single_class_channel_user_list(class_id)

	def get_single_channel_user_list (self, team_id, channel_name):
		# get list of current users in channel
		response = self.process.run_command(
			f'Get-TeamChannelUser -GroupId {team_id} -DisplayName "{channel_name}"',
			convert_json = True
		)

		# parse response
		# if channel not found, stop
		if (type(response) == 'str' and response.find('Channel not found') != -1):
			return False
		else:
			# feed data into list
			member_list = {}

			for d in response:
				userid = d['User'].lower().replace('@ad.unsw.edu.au','')  # 'User ' = accountname@domain
				member_list[userid] = User(
					userid,    # zID
					d['Name']  # name
				)

			print(f'USER LIST for {channel_name}')
			for u in member_list:
				print(member_list[u])

			return member_list

	def get_single_class_channel_user_list (self, class_id):
		cl = self.classes_list[class_id]

		cl['teams_user_list'] = self.get_single_channel_user_list(cl.teams_group_id, cl.name)

	def create_channels (self, channel_type='Private', owners=[]):
		for class_id in self.classes_list:
			self.create_single_channel(class_id, channel_type, owners)

	def create_single_channel (self, class_id, channel_type='Private', owners=[]):
		cl = self.classes_list[class_id]

		# create channel
		response = self.process.run_command(
			'New-TeamChannel -GroupId {TEAMS_GROUP_ID} -DisplayName "{CHANNEL_NAME}" -MembershipType {TYPE}'.format(
				TEAMS_GROUP_ID = cl.teams_group_id,
				CHANNEL_NAME   = cl.name,
				TYPE           = channel_type
				# OWNER          = owners[0]  # -Owner {OWNER} can't work with public channels, defaults to connected user otherwise
			)
		)

		# TODO parse response
		# if (response.find(''))

		self.log(f'Created channel for class {cl}')

		# if all good, set owners
		for o in owners:
			self.add_user_to_class_channel(class_id, user=o, role='Owner')

	# convenience function to add a single user to all channels at once
	def add_user_to_all_class_channels (self, user=User, role='Member', course_list=[]):
		for class_id in self.classes_list:
			cl  = self.classes_list[class_id]

			# check if we exclude courses
			if (len(course_list) > 0 and cl.course not in course_list):
				continue  # skip this iteration and move on

			self.add_user_to_class_channel(cl.id, user, role)

	# TODO deprecate this function
	def add_user_to_class_channel (self, class_id, user=User, role='Member'):
		cl           = self.classes_list[str(class_id)]
		team_id      = cl['teams_group_id']
		channel_name = cl['name']

		return self.add_user_to_channel(team_id, channel_name, user, role)

	def add_user_to_channel (self, team_id, channel_name, user=User, role='Member'):
		# add to relevant channel
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


	def remove_user_from_class_channel (self, class_id, user=User, role='Member'):
		cl = self.classes_list[str(class_id)]

		# add to relevant channel
		response = self.process.run_command(
			'Remove-TeamChannelUser -GroupId {TEAMS_GROUP_ID} -DisplayName "{CHANNEL_NAME}" -User {USER}'.format(
				TEAMS_GROUP_ID = cl['teams_group_id'],
				CHANNEL_NAME   = cl['name'],
				USER           = f'{user.id}@ad.unsw.edu.au'
			)
		)

		# TODO parse response
		# Remove-TeamChannelUser: Error occurred while executing 
		# Code: NotFound
		# Message: Not Found
		# InnerError:
		# RequestId: 55982b3c-1319-4614-97bf-68e67ea94f90
		# DateTimeStamp: 2020-09-19T23:46:30
		# HttpStatusCode: NotFound
		success = True

		self.log(f'Class {cl}: Removed {user} as {role}')

		return success

	def update_channels (self):
		total_count_removed = 0
		total_count_added   = 0

		for class_id in self.classes_list:
			(r, a) = self.update_single_channel(class_id)

			total_count_removed += r
			total_count_added   += a

		self.log(f'Updating all channels (totals: - {total_count_removed} / + {total_count_added})')

	def update_single_class_channel (self, class_id):
		cl = self.classes_list[str(class_id)]
		self.log(f"Updating class {cl} ({len(cl['desired_user_list'])} enrolments)")

		count_removed = 0
		count_added   = 0

		# check current teams list against desired list
		#	remove any not on desired list (but check against whitelist, those are save from deletion)
		for user_in_teams_list in cl['teams_user_list']:
			if (user_in_teams_list not in cl['desired_user_list'] and user_in_teams_list not in self.user_whitelist):
				response = self.remove_user_from_class_channel(class_id, cl['teams_user_list'][user_in_teams_list])
				
				if (response):
					count_removed += 1
				
		# add any not in teams list but on desired list
		for user_in_desired_list in cl['desired_user_list']:
			if (user_in_desired_list not in cl['teams_user_list']):
				response = self.add_user_to_class_channel(class_id, cl['desired_user_list'][user_in_desired_list])
				
				if (response):
					count_added += 1

		self.log(f'Updating class {cl} complete (- {count_removed} / + {count_added})')

		return (count_removed, count_added)

	# see: https://docs.microsoft.com/en-us/powershell/module/teams/new-team?view=teams-ps
	# info parameter isn't required for anything but may be useful to parse the logs and keep team data and other info together.
	def create_team (self, name, description='', visibility='Private', owners=[], info=''):
		
		# TODO improve this by using convert_json = True to get team object in one go
		# create team
		response = self.process.run_command(
			f'$group = New-Team -DisplayName "{name}" -Description "{description}" -Visibility {visibility}'
		)
		# parse response (returns a Group object with GroupID for the newly created team)
		response_group_id = self.process.run_command('$group.GroupId')

		
		# check for group_id format: 458b02e9-dea0-4f74-8e09-93e95f93b473
		if (not re.match('^[\dabcdef-]{36}$', response_group_id)):
			self.log(f'Failed to create {visibility.lower()} team {name} (response: {response_group_id}) ({info=})', 'ERROR')
		else:
			self.log(f'Created {visibility.lower()} team {name} ({response_group_id}) ({info=})')

			self.add_users_to_team(response_group_id, owners, 'Owner')

	def get_single_team_user_list (self, team_id, role='Member'):
		# get list of current users in team
		# TODO handle the optional role parameter as filter
		response = self.process.run_command(
			f'Get-TeamUser -GroupId {team_id}',
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
				userid = d['User'].lower().replace('@ad.unsw.edu.au','')  # 'User ' = accountname@domain
				user_list[userid] = User(
					userid,    # zID
					d['Name']  # name
				)

			print(f'USER LIST for {team_id}')
			for k in user_list:
				print(user_list[k])

			return user_list

	def update_single_team (self, team_id, team_user_list, desired_user_list):
		# TODO
		print('ERROR: Not implemented yet')

	def remove_users_from_team (self, team_id, users=[User], role='Member'):
		for u in users:
			self.remove_user_from_team(team_id, u, role)

	def remove_user_from_team (self, team_id, user=User, role='Member'):
		# removing a user as role='Owner' keeps them as a team member
		response = self.process.run_command(
			f'Remove-TeamUser -GroupId {team_id} -User {user.id}@ad.unsw.edu.au -Role {role}'
		)

		self.log(f'Team {team_id}: Removed {user} as {role}')

	def add_users_to_team (self, team_id, users=[User], role='Member'):
		for u in users:
			self.add_user_to_team(team_id, u, role)

	def add_user_to_team (self, team_id, user=User, role='Member'):
		# adding an owner, if new, also means the user is added as a member to that team
		response = self.process.run_command(
			f'Add-TeamUser -GroupId {team_id} -User {user.id}@ad.unsw.edu.au -Role {role}'
		)

		self.log(f'Team {team_id}: Added {user} as {role}')

	def add_tab_to_channel (self, teams_group_id, channel_name, tab_info):
		self.log('You cannot add tabs to channels yet...','ERROR')
		
		# no cmdlet available yet for Module MicrosoftTeams, but sharepoint-pnp has one 
		#   Install-Module SharePointPnPPowerShellOnline
		#   now, login with devicelogin and provide sharepoint site url (e.g., https://unsw.sharepoint.com/sites/DesignNext2)
		#   note that this login only works for one team/sharepoint site at a time :(
		#   Connect-PnPOnline -PnPO365ManagementShell
		#   also needs admin permissions beyond what a regular user has :(
		#   so best to wait until its supported in the Teams module
		response = self.process.run_command(
			'Add-PnPTeamsTab -Team {TEAMS_GROUP_ID} -Channel "{CHANNEL_NAME}" -DisplayName "{TAB_NAME}" -Type {TAB_TYPE} -ContentUrl "{CONTENT_URL}"'.format(
				TEAMS_GROUP_ID = teams_group_id,
				CHANNEL_NAME   = channel_name,
				TAB_NAME       = tab_info['name'],
				TAB_TYPE       = tab_info['type'],
				CONTENT_URL    = tab_info['url']
			)
		)

	# convenience function to find particular users
	def find_users (self, list_to_search, search_key, search_value):
		results = []

		# check if list is actually a dict, and if so convert
		if (isinstance(list_to_search, dict)):
			list_to_search = list(list_to_search.values())

		for user in list_to_search:
			# check whether we match (part of) a string or other types of values
			if (isinstance(search_value, str)):
				if (user[search_key].lower().find(search_value.lower()) != -1):
					results.append(user)
			else:
				if (user[search_key] == search_value):
					results.append(user)

		return results
				
	def log (self, action='', type='INFO'):
		print(f'{type} - {action}')
		self.log_file.write(f'\n{datetime.now()} {type} - {action}')
		# ensure it is written rightaway to avoid loss of log data upon a crash
		self.log_file.flush()


###
# a simple method to download a user list CSV file from Moodle
# course id is unique on Moodle, look at the url to find the id for your course
###
class MoodleUpdater:
	def __init__ (self, course_id, username, password):
		self.course_id = course_id
		self.csv_file  = None
		self.logged_in = False

		self.login(username, password)

	def login (self, username, password):
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
		# don't need the browser anymore
		self.browser.quit()

	# so we can use the with statement
	def __enter__ (self):
		return self

	# so we can exit after using the with statement
	def __exit__ (self, type, value, traceback):
		self.close()

		if (traceback is None):  # no exception occured
			pass
		else:
			return False  # re-raise the exception to be transparent

	def get_users_csv (self):
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

	# EXPERIMENTAL - completely untested
	def add_gradebook_category (self, category_info={}):
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

	# TODO
	def add_section (self, section_info={}):
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


# -----------------------------------------------------------------------------


if __name__ == '__main__':
	login = LoginData()

	# with MoodleUpdater(54605, login.username, login.password) as mu:
	# 	my_path = mu.get_users_csv()

	# basic operation by default
	with TeamsUpdater(my_path, my_classes_list, my_user_whitelist) as tu:
		# connect at the start - everything else depends on this working
		# tu.connect('automated', login.username, login.password)
		
		# import data first - later steps build on this
		tu.import_user_list()
		# tu.get_channels_user_list()

		# sync up channels - with many users, this takes a long time (approx 8 commands/minute)
		# tu.update_channels()
