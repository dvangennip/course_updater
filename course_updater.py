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

import pandas as pd
from datetime import datetime
import subprocess
import time
import os
import fcntl
import re
import getpass
import webbrowser

# improve this based on argparse lib if I have time
# print('\nTEAMS UPDATE CHANNEL SCRIPT')
# print('\nDownload student data from Moodle by selecting all active users, then choose "Download as CSV file". This file should include a column named Class ID. Put the downloaded CSV file in the same folder as this script.\n')

# it it assumed Teams are already created and that students are auto-added to teams
#	this script is only concerned with keeping private channels in sync with the Moodle list

# make sure that for each tutorial-like ClassID, there is a corresponding private channel
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

		# run a few commands as a self test
		self.run_command('nothing - just letting it settle', False)
		self.run_command('clear')

	def close (self):
		# disconnect and confirm any prompts that may come our way
		if (self.connected_to_teams):
			self.run_command('Disconnect-MicrosoftTeams')

		self.process.stdin.close()
		self.process.kill()

	def run_command (self, command, do_run=True):
		self.count += 1
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
			time.sleep(0.5)

			while True:
				try:
					# read stdout line by line
					# this makes it easier to pick up significant bits of data
					o = self.process.stdout.readline()

					if re.match('PS .+?>\s{0,1}$', o) is not None:
						# print('~~~~ REGEX MATCH - BREAKING LOOP ~~~~')
						break
					elif (o == command or o == command + '\n'):  # linefeed is usually added
						pass  # no need to save this
					else:
						output += o
						if (self.debug_mode):
							print(o, end='')  # avoid double linefeeds when printing

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

		self.latest_output = output

		# log command and output data for debugging purposes
		if (self.debug_mode):
			with open(f'cmd_logs/cmd_{self.count}.txt','w') as f:
				f.write(f'COMMAND: {command}\n\n')
				f.write(output)

		return output

	def connect_to_teams (self, use_popup=True, username=None, password=None):
		if (self.connected_to_teams):
			return True
		else:
			response = ''

			if (use_popup):
				# login via a browser window/popup
				# works but needs user input via browser
				webbrowser.open('https://microsoft.com/devicelogin')
				response = self.run_command('Connect-MicrosoftTeams')

			else:
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

	def parse_common_errors (self, input_string=''):
		# TODO check for typical errors
		#'You must call the Connect-MicrosoftTeams cmdlet before calling any other cmdlets.'
		if (input_string.find('You must call the Connect-MicrosoftTeams cmdlet before calling any other cmdlets.')):
			return False

	# parses command output that represents tabular data
	# each header item is a string denoting that response table header name
	def parse_response_table (self, input_string='', headers=[]):
		# get rid of everything before the first table header text
		x            = input_string.find(headers[0])
		input_string = input_string[x:]

		# get rid of everthing after the table (indicated by double new linefeed characters)
		x            = input_string.find('\n\n')
		input_string = input_string[:x]

		# split into lines
		tl = input_string.split('\n')

		# --- parse each header

		header_data = []

		# work backwards so later results are available for the end variable
		for hi in range(len(headers)-1,-1,-1):
			h = headers[hi]
			
			end = 0
			if (hi == len(headers)-1):
				# pick line end. on header line, end is immediately after text, so pick another line
				end = len(tl[1]) -1
			else:
				# pick the start of the previous one
				end = header_data[0]['start']-1
			
			hdata = {
				'name' : h,
				'start': tl[0].find(h),
				'end'  : end
			}

			header_data.insert(0,hdata)
		
		# --- parse lines for data

		row_data = []

		for i in range(2,len(tl)):
			d = {}

			for he in header_data:
				d[he['name']] = tl[i][he['start'] : he['end']].lstrip().rstrip()
			
			row_data.append(d)

		return row_data


###
# Wrapper around powershell teams commands, with additional logic to help with
# generating channels and keeping users in sync with an external file.
###
class TeamsUpdater:
	def __init__ (self, path=None, classes={}, whitelist={}, process=None):
		# TODO replace by file connection
		self.log_list        = []
		
		self.data_path       = path
		if (path is None):
			self.log('Please provide a filepath to a CSV file that TeamsUpdater can read.', 'ERROR')
			raise FileNotFoundError

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

		# open log file
		self.log_file = open('teams_updater.log', 'a')
		self.log_file.write('\n\n\n~~~ NEW LOG ~~~ ~~~ ~~~ ~~~')
	
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
	
	def connect (self):
		# get connected early -> this way later commands that require a connection won't fail
		self.connected = self.process.connect_to_teams()

	def close (self):
		# cleanup any open connections, files open
		if (self.process is not None):
			self.process.close()
		self.log_file.close()

	def get_all_data (self):
		self.import_user_list()
		self.get_channels_user_list()

	def import_user_list (self):
		self.log(f'Importing data from: {self.data_path}')

		unknown_class_ids = []
		
		# open and read CSV file - assumes existence of columns named Username (for zID), First Name, Surname
		dataframe = pd.read_csv(self.data_path)
		
		# for every user, add them to the known class lists
		#	when complete, this gives a complete view of users in each class
		for index, user in dataframe.iterrows():
			user_id = user['Username'].lower()  # make sure it's all lowercase, for later comparisons

			new_user = User(
				user_id,
				user['First name'] + ' ' + user['Surname']
			)

			# users without classes assigned get added to the whitelist
			# in Moodle, more or less by definition, no ClassID -> instructor
			if (user['Class ID'] == '-'):
				# do another check to make sure this user is actually staff
				if (user['Group1'].find('Staff') != -1):
					new_user.owner = True

					# don't overwrite prior whitelist user data
					if (user_id not in self.user_whitelist.keys()):
						self.user_whitelist[user_id] = new_user
				else:
					self.log(f'User {new_user} has no Class IDs but is not a staff member: skipped.', 'WARNING')
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

		# sort the unknown class ids from low to high (requires intermediate conversion to int)
		unknown_class_ids = list(map(int, unknown_class_ids))
		unknown_class_ids.sort()
		unknown_class_ids = list(map(str, unknown_class_ids))
		self.log(f'No class items that match Class IDs {", ".join(unknown_class_ids)}')

		self.log(f'Imported data on {len(dataframe.index)} users.\n\n')

	def get_channels_user_list (self):
		# iterate over each relevant Class ID
		for class_id in self.classes_list:
			self.get_single_channel_user_list(class_id)

	def get_single_channel_user_list (self, class_id):
		cl = self.classes_list[class_id]

		# get list of current users in channel
		response = self.process.run_command(
			'Get-TeamChannelUser -GroupId {TEAMS_GROUP_ID} -DisplayName "{CHANNEL_NAME}"'.format(
				TEAMS_GROUP_ID = cl.teams_group_id,
				CHANNEL_NAME   = cl.name
			)
		)

		# parse response
		# if channel not found, stop
		if (response.find('Channel not found') == -1):
			data = self.process.parse_response_table(response, ['UserId', 'User ', 'Name'])

			# feed data into class list
			for d in data:
				userid = d['User '].lower().replace('@ad.unsw.edu.au','')  # 'User ' = accountname@domain
				cl['teams_user_list'][userid] = User(
					userid,    # zID
					d['Name']  # name
				)
		else:
			return False

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
			self.add_user_to_channel(class_id, user=o, role='Owner')

	# convenience function to add a single user to all channels at once
	def add_user_to_all_channels (self, user=User, role='Member', course_list=[]):
		for class_id in self.classes_list:
			cl  = self.classes_list[class_id]

			# check if we exclude courses
			if (len(course_list) > 0 and cl.course not in course_list):
				continue  # skip this iteration and move on

			self.add_user_to_channel(cl.id, user, role)

	def add_user_to_channel (self, class_id, user=User, role='Member'):
		cl = self.classes_list[str(class_id)]

		# add to relevant channel
		response = self.process.run_command(
			'Add-TeamChannelUser -GroupId {TEAMS_GROUP_ID} -DisplayName "{CHANNEL_NAME}" -User {USER}'.format(
				TEAMS_GROUP_ID = cl['teams_group_id'],
				CHANNEL_NAME   = cl['name'],
				USER           = '{id}@ad.unsw.edu.au'.format(id=user.id)
			)
		)

		# owners needs to be added as regular members first, then set to owner status
		if (response.find('User is not found in the team.') == -1 and role == 'Owner'):
			response = self.process.run_command(
				'Add-TeamChannelUser -GroupId {TEAMS_GROUP_ID} -DisplayName "{CHANNEL_NAME}" -User {USER} -Role {ROLE}'.format(
					TEAMS_GROUP_ID = cl['teams_group_id'],
					CHANNEL_NAME   = cl['name'],
					USER           = f'{user.id}@ad.unsw.edu.au',
					ROLE           = role
				)
			)

		# parse response
		success = True
		if (response.find('Could not find member.') != -1):
			success = False

		self.log(f'Class {cl}: Added {user} as {role}')

		return success

	def remove_user_from_channel (self, class_id, user=User, role='Member'):
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
		success = True

		self.log(f'Class {cl}: Removed {user} as {role}')

		return success

	def update_channels (self):
		for class_id in self.classes_list:
			self.update_single_channel(class_id)

	def update_single_channel (self, class_id):
		cl = self.classes_list[str(class_id)]
		self.log(f"\nUpdating class {cl} ({len(cl['desired_user_list'])} enrolments)")

		count_removed = 0
		count_added   = 0

		# check current teams list against desired list
		#	remove any not on desired list (but check against whitelist, those are save from deletion)
		for user_in_teams_list in cl['teams_user_list']:
			if (user_in_teams_list not in cl['desired_user_list'] and user_in_teams_list not in self.user_whitelist):
				response = self.remove_user_from_channel(class_id, cl['teams_user_list'][user_in_teams_list])
				
				if (response):
					count_removed += 1
				
		# add any not in teams list but on desired list
		for user_in_desired_list in cl['desired_user_list']:
			if (user_in_desired_list not in cl['teams_user_list']):
				response = self.add_user_to_channel(class_id, cl['desired_user_list'][user_in_desired_list])
				
				if (response):
					count_added += 1

		self.log(f'Updating class {cl} complete (- {count_removed} / + {count_added})')

	# see: https://docs.microsoft.com/en-us/powershell/module/teams/new-team?view=teams-ps
	# info parameter isn't required for anything but may be useful to parse the logs and keep team data and other info together.
	def create_team (self, name, description='', visibility='Private', owners=[], info=''):
		
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


if __name__ == '__main__':
	# basic operation by default
	with TeamsUpdater(my_path, my_classes_list, my_user_whitelist) as tu:
		# connect at the start - everything else depends on this working
		tu.connect()
		
		# import data first - later steps build on this
		tu.import_user_list()
		tu.get_channels_user_list()

		# sync up channels - with many users, this takes a long time (approx 8 commands/minute)
		tu.update_channels()
