#!/usr/bin/python3

#####
# script requires python version 3.7+, powershell 7+, and the PS Teams module to be installed
# only tested on macOS 10.15+
#
# generally, this script is as resilient as a toddler with icecream in their hand
# it will drop and create a scene at some stage...
#####

from dataclasses import dataclass, field
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
import sys
import colorama


# -----------------------------------------------------------------------------


@dataclass
class User:
	"""
	Class that holds user data
	"""
	id                       : str
	name                     : str
	course_code              : str  = ''
	class_ids                : list = field(default_factory=list)
	groups                   : list = field(default_factory=list)
	groupings                : list = field(default_factory=list)
	email                    : str  = ''
	owner                    : bool = False  # 'Member'|'Owner'
	classes                  : list = field(default_factory=list)
	project                  : str  = ''
	project_team             : str  = ''
	tech_stream              : str  = ''
	course_coordinators      : list = field(default_factory=list)
	project_coordinators     : list = field(default_factory=list)
	project_mentors          : list = field(default_factory=list)
	tech_stream_coordinators : list = field(default_factory=list)
	tech_stream_mentors      : list = field(default_factory=list)

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
		self.app_id = 'PY_COURSE_UPDATER'

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


class Logger:
	"""
	Class for a logger object that appends logs to a text file.
	Useful to track what is happening.
	Comes with colour coding and several log levels (info, confirm, debug, warning, error),
	although it currently just outputs all levels to the logfile.
	"""
	def __init__ (self):
		# helper library for adding colours to output
		colorama.init()

		# open log file
		self.log_file = open('course_updater.log', 'a')
		self.log_file.write('\n\n\n~~~ NEW LOG ~~~ ~~~ ~~~ ~~~')

	def log (self, message, level='INFO'):
		full_message = f'{level} - {message}'

		# add colour coding to terminal output
		if (level == 'CONFIRM'):
			print(f'{colorama.Style.BRIGHT}{colorama.Fore.GREEN}{full_message}{colorama.Style.RESET_ALL}')
		elif (level == 'DEBUG'):
			print(f'{colorama.Fore.BLUE}{full_message}{colorama.Style.RESET_ALL}')
		elif (level == 'WARNING'):
			print(f'{colorama.Fore.MAGENTA}{full_message}{colorama.Style.RESET_ALL}')
		elif (level == 'ERROR'):
			print(f'{colorama.Style.BRIGHT}{colorama.Back.RED}{colorama.Fore.WHITE}{full_message}{colorama.Style.RESET_ALL}')
		else:
			print(full_message)

		self.log_file.write(f'\n{datetime.now()} {full_message}')
		# ensure it is written rightaway to avoid loss of log data upon a crash
		self.log_file.flush()

	def info (self, message):
		self.log(message)

	def confirm (self, message):
		self.log(message, 'CONFIRM')

	def debug (self, message):
		self.log(message, 'DEBUG')

	def warning (self, message):
		self.log(message, 'WARNING')

	def error (self, message):
		self.log(message, 'ERROR')

	def close (self):
		self.log_file.close()

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


class Notifier:
	""" basic class to send OS-style notifications """
	@staticmethod
	def notify (title='Updater notification', message='', sound='Submarine'):
		if (sys.platform == 'darwin'):
			os.system(f"""osascript -e 'display notification "{message}" with title "{title}" sound name "{sound}"'""")


# -----------------------------------------------------------------------------


class PowerShellWrapper:
	"""
	this is what happens when you know python and think you'll just call
	some powershell commands, only to realise when you're in knee-deep that
	the login step requires the shell process to stay alive between calls
	and now you have to tame powershell somehow, making you wonder if simply
	learning powershell in the first place wouldn't have been a better bet...
	
	enter this wrapper class... squarely aimed at using the same shell for everything.
	handles powershell commands in the background, works kind of like the
	`pexpect` library, listening and returning only when it encounters the
	reappearing prompt or another string in the output that we want to stop at.
	
	very simple, very likely not to work with most edge cases.
	"""
	def __init__ (self, lazy_start=False, debug=True, login_method=None, username=None, password=None):
		self.latest_output      = ''
		self.connected_to_teams = False
		self.count              = 0
		self.process            = None
		self.debug_mode         = debug
		self.username           = username
		self.password           = password
		self.login_method       = login_method

		if (self.debug_mode):
			try:
				self.log = open('cmd_logs/alog.txt', 'w')
			except FileNotFoundError as e:
				print('\nHINT: ensure the cmd_logs directory exists.\n')
				raise  # bare re-raise so no losing stack trace

		if (lazy_start is False):
			self.ensure_started()

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

	def ensure_started (self):
		if (self.process is None):
			self.process = subprocess.Popen(
				['pwsh'],
				stdin    = subprocess.PIPE,
				stdout   = subprocess.PIPE,
				stderr   = subprocess.STDOUT,
				encoding = 'utf-8'
			)
			fcntl.fcntl(self.process.stdout.fileno(), fcntl.F_SETFL, os.O_NONBLOCK)

			# run a few commands as a self test
			time.sleep(5)
			self.run_command('nothing - just letting it settle', False)
			time.sleep(5)
			self.run_command('Write-Output "check"')

	def close (self):
		# disconnect and confirm any prompts that may come our way
		if (self.connected_to_teams):
			self.run_command('Disconnect-MicrosoftTeams')

		if (self.process != None):
			self.process.stdin.close()
			self.process.kill()

		if (self.debug_mode):
			self.log.close()

	def run_command (self, command, do_run=True, delay=0.5, return_if_found=None, convert_json=False):
		"""
		The shakily beating heart of this wrapper.
		It takes a command and feeds that into the powershell process, parsing any output it generates.

		This method returns whenever it re-encounters the command prompt, which is usually the signal that a command was processed.
		Alternatively, passing a string to `return_if_found` will stop once that string is encountered in the process output.

		Set `convert_json` to True when expecting output that can be parsed into JSON.
		"""
		self.ensure_started()

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
				try:
					output = json.loads(output)
				except json.decoder.JSONDecodeError as e:
					print(e)
			# else just keep output unconverted

		self.latest_output = output

		# log command and output data for debugging purposes
		if (self.debug_mode):
			with open(f'cmd_logs/cmd_{self.count}.txt','w') as f:
				f.write(f'COMMAND: {command}\n\n')
				f.write(str(output))   # making sure this is always a string

		return output

	def connect_to_teams (self):
		"""
		Running any commands from the MicrosoftTeams pwoershell module requires an active login
		This method logs in automatically, either by just giving a popup or by attempting a fully
		automatic login by hiding the Office365 login process via a headless browser connection.

		TODO: automated seems broken in some cases at the moment... still opens browser tab that works.
		"""
		self.ensure_started()

		if (self.connected_to_teams):
			return True
		else:
			response = ''

			if (self.login_method == None or self.login_method == 'popup' or self.login_method == 'default'):
				# login via a browser window/popup - works but needs user input via browser
				response = self.run_command('Connect-MicrosoftTeams')
			else:
				# get username and password
				if (self.username is None):
					self.username = input('Username: ')
				if (self.username.find('@') == -1):
					self.username += '@ad.unsw.edu.au'
				
				if (self.password is None):
					self.password = getpass.getpass(prompt='Password: ')

				if (self.login_method == 'automated'):
					# login via browser window but automate all actions
					try:
						b = Browser('firefox', headless=False, incognito=True)
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
						b.fill('loginfmt', self.username)
						b.find_by_id('idSIButton9').click()
						# wait for next page
						time.sleep(2)

						# second up, password
						b.fill('passwd', self.password)
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
				elif (self.login_method == 'credentials'):
					# note: this procedure doesn't work because basic authentication uni tenant doesn't support the right sign-on protocols
					#       would be cool though...

					# first, setup a credential object based on login details
					self.run_command(f'$User = "{self.username}"')
					self.run_command(f'$PWord = ConvertTo-SecureString -String "{self.password}" -AsPlainText -Force')
					self.run_command('$Credential = New-Object -TypeName System.Management.Automation.PSCredential -ArgumentList $User, $PWord')
					
					# use credentials to connect (avoids a user prompt)
					response = self.run_command('Connect-MicrosoftTeams -Credential $Credential')
			
			# check for succesful connection
			if (response.find('Token Acquisition finished successfully. An access token was returned')):
				self.connected_to_teams = True
			elif (response.find('TenantId')):  # just some string that will show only if succesful
				self.connected_to_teams = True

			return self.connected_to_teams


class TeamsUpdater:
	"""
	Wrapper around powershell MicrosoftTeams module commands, with additional logic to keep teams and channels in sync with an external list.
	"""
	def __init__ (self, path=None, stafflist={}, process=None, username=None, password=None, logger=None, prevent_self_removal=True):
		if (logger == None):
			self.logger = Logger()
		else:
			self.logger = logger

		# init variables
		self.data_path       = path
		if (self.data_path is None):
			self.logger.warning('Please provide a filepath to a CSV file that TeamsUpdater can read.')
			# raise FileNotFoundError

		# create stafflist from input list
		# note that the list isn't technically a list but rather a dictionary
		# dicts have the benefit that we can match by id/key value rightaway
		# not optimal from a neatness point of view but it works fine
		self.user_stafflist  = {}
		for name in stafflist:
			self.user_stafflist[str(name.id)] = name

		# master user list (idem, a dict not a list)
		self.user_list       = {}

		# user ids that should not be touched as these are uni-managed service accounts
		self.exclusion_ids = ['svco365teamsmanage']

		self.connected = False
		self.username  = username
		self.password  = password

		# assign existing external process to connect to powershell
		self.process   = process

		if (self.process is None):
			self.process_internal = True
			self.process          = PowerShellWrapper(lazy_start=True, login_method='credentials', username=self.username, password=self.password)
		else:
			self.process_internal = False

		# optionally, safeguard against self-removal
		if (prevent_self_removal):
			if (self.username == None):
				self.username = self.process.username
			self.exclusion_ids.append( self.username.replace('@ad.unsw.edu.au','') )

		# temp variables
		self.user_channel_bug_counter = 0
	
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
		if (self.connected == False):
			self.logger.info('Connecting to Teams via PowerShellWrapper')
			self.connected = self.process.connect_to_teams()

			# try again if we're connected
			if (self.connected):
				self.logger.confirm('Connected to Teams')
			else:
				self.logger.error('Not connected to Teams. Expect trouble...')

		return self.connected
	
	def close (self):
		""" cleanup any open connections, files open """
		if (self.process is not None and self.process_internal):
			self.process.close()

	def import_user_list (self, course_code, coordinators, project_list, tech_stream_list=None):
		"""
		Imports a user list csv file that was exported from Moodle
		"""
		self.logger.info(f'Importing data from: {self.data_path}')

		count_total       = 0
		count_instructors = 0
		count_students    = 0
		count_unknown     = 0

		groups_dict       = {}  # example: {'9383': ['Students Grouping - Project X','Students Grouping (All)']}

		# ----- STEP 1 - IMPORT DATA ----

		# before importing user data, get grouping data ready for later merging
		try:
			with open(self.data_path.replace('.csv', '_groupings.json'), 'r') as fg:
				groups_dict = json.loads( fg.read() )
		except FileNotFoundError as e:
			self.logger.error(e)
		
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
					# number of groups shown in Moodle export varies depending on number of groups in use
					# so we attempted to range over a large number and fail at some point -> expected, so we can ignore it
					pass

				# create User class from compiled info
				new_user = User(
					user_id,
					user['First name'] + ' ' + user['Surname'],
					course_code,
					class_ids,
					user_groups,
					user_groupings,
					user['Email address']
				)

				# users without classes assigned get added to the stafflist
				# in Moodle, no ClassID means the user is staff or a student halfway through unenrolment
				if (user['Class ID'] == '-'):
					# do a check to make sure this user is actually staff
					#   adding a user to this group requires manual assignment in Moodle
					#   as an alternative, you can add them into the user stafflist passed in at the start
					if (new_user.in_group('Staff (DO NOT REMOVE)')):
						new_user.owner = True

						# don't overwrite prior stafflist user data
						if (user_id not in self.user_stafflist):
							self.user_stafflist[user_id] = new_user

						count_instructors += 1
					else:
						self.logger.log(f'User {new_user} has no Class IDs but is not a staff member: skipped.', 'WARNING')
						count_unknown += 1
				else:
					# add new to master list
					self.user_list[user_id] = new_user

					count_students += 1

		# ----- STEP 2 - ADDITIONAL PARSING -----

		# do additional parsing on users to extract useful data
		for sid in self.user_list:
			s = self.user_list[sid]

			# avoid including staff (who have no class ids) and partially unenrolled students (also no class ids)
			if (len(s.class_ids) == 0):
				continue

			# add main coordinator info
			for index, c in enumerate(coordinators):
				if c in self.user_stafflist:
					s.course_coordinators.append(c)

			# loop over all groups to extract useful info
			for g in s.groups:

				# --- class ID-based matching below (fits most courses)
				
				if ( g.isdigit() ):
					# find the relevant project
					for pkey in project_list:
						p = project_list[pkey]
						
						# main_class_id may not exists for courses where it's irrelevant
						if ('main_class_id' in p and p['main_class_id'] == int(g)):
							s.project = pkey
							# if matching project is found, no need to continue the for loop trying other projects
							break
						elif ('classes' in p):
							for cl in p['classes']:
								if (cl['class_id'] == int(g)):
									# lectures are not included as classes
									if (cl['name'].find('LE') != -1):
										pass
									# labs are handled separately from regular classes
									elif (cl['name'].find('LAB') != -1):
										s.tech_stream += f"{cl['name']}_{cl['class_id']}  [ {cl['description']} ]"
										
										# add demonstrator info
										for did in cl['instructors']:
											# ensure there is indeed data on a listed demonstrator
											if (did in self.user_stafflist):
												s.tech_stream_mentors.append(did)
									# regular classes
									else:
										s.classes.append(f"{cl['name']}_{cl['class_id']}  [ {cl['description']} ]")
										
										# add demonstrator info
										for did in cl['instructors']:
											# ensure there is indeed data on a listed demonstrator
											if (did in self.user_stafflist):
												s.project_mentors.append(did)

				# --- group name based matching below (fits ENGG1000 best)

				# TODO generalise to allow other terms than 'Project'
				if (g.find('Project Group - ') != -1):
					s.project = re.sub(
						r'Project Group - (?P<project>.+?)',  # original   # include \(.+?\) at end to catch (Online|On Campus)
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
					for su in self.user_stafflist:
						mu = self.user_stafflist[su]

						# match against lower case to avoid minor spelling issues to cause mismatches
						if (mu.name.lower() == pmentor.lower()):
							s.project_mentors.append(mu.id)

				# extract tech stream data
				if (tech_stream_list is not None):
					if (g.find('Technical Stream Group - ') != -1):
						s.tech_stream = g.replace('Technical Stream Group - ','').replace(' (OnCampus)','').replace(' (Online)','')

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
							for su in self.user_stafflist:
								mu = self.user_stafflist[su]

								# match against lower case to avoid minor spelling issues to cause mismatches
								if (mu.name.lower() == tmentor.lower()):
									s.tech_stream_mentors.append(mu.id)

				# --- common matching continues below
				
				# find project team
				if (g.lower().find('team') != -1 and g.lower().find('stream') == -1):
					s.project_team = g.replace('Project ','').replace('Student Teams - ','')
			
			# --- below we assume project and streams have been found

			if (len(s.project) > 0):
				s.project_coordinators = project_list[s.project]['coordinators']

			if (tech_stream_list is not None and len(s.tech_stream) > 0):
				s.tech_stream_coordinators = tech_stream_list[s.tech_stream]['coordinators']

		count_total = count_students + count_instructors + count_unknown
		self.logger.log(f'Imported data on {count_total} users (students: {count_students}, instructors: {count_instructors}, unknown: {count_unknown}).\n\n')

	def export_student_list (self, replace_terms=None):
		""" Exports a list of students using User class information """

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

			""" internal parse function to go from user_id to name and email """
			def _parse_ids_to_names_emails (id_list):
				ids    = '-'
				names  = '-'
				emails = '-'

				if (len(id_list) > 0):
					ids = ','.join(id_list)
					names  = []
					emails = []

					for index, c in enumerate(id_list):
						if c in self.user_stafflist:
							names.append(  self.user_stafflist[c].name  )
							emails.append( self.user_stafflist[c].email )
						else:
							names.append(  'Unknown staff'    )
							emails.append( f'{c}@unsw.edu.au' )

				return ids, ', '.join(names), ', '.join(emails)
			
			# iterate over all students
			for sid in self.user_list:
				s = self.user_list[sid]

				# avoid including staff (who have no class ids) and partially unenrolled students (also no class ids)
				if (len(s.class_ids) == 0):
					continue

				# fill in staff info
				ccoordinator_id, ccoordinator, ccoordinator_em = _parse_ids_to_names_emails(s.course_coordinators)
				pcoordinator_id, pcoordinator, pcoordinator_em = _parse_ids_to_names_emails(s.project_coordinators)
				pmentor_id, pmentor, pmentor_em                = _parse_ids_to_names_emails(s.project_mentors)
				tcoordinator_id, tcoordinator, tcoordinator_em = _parse_ids_to_names_emails(s.tech_stream_coordinators)
				tmentor_id, tmentor, tmentor_em                = _parse_ids_to_names_emails(s.tech_stream_mentors)

				# finally, write output for this student
				f.write(f'\n{s.id},{s.name},{s.email},"{",".join(map(str,s.class_ids))}",{s.course_code},"{ccoordinator}","{ccoordinator_id}","{ccoordinator_em}",{s.project},"{pcoordinator}","{pcoordinator_id}","{pcoordinator_em}","{",".join(s.classes)}","{pmentor}","{pmentor_id}","{pmentor_em}","{s.project_team}","{s.tech_stream}","{tcoordinator}","{tcoordinator_id}","{tcoordinator_em}","{tmentor}","{tmentor_id}","{tmentor_em}"')

			self.logger.log(f'Exported student list to {output_path}\n\n')

	def export_class_list (self, project_list):
		""" Exports a list of classes with instructor information """

		# assume course code is first thing in path, for example: engg1000-title---2021-t1.csv
		course = self.data_path[:self.data_path.find('-')]
		
		output_path = self.data_path.replace('.csv', '-classes.csv')

		with open(output_path, 'w') as f:
			# write out header
			header = 'Stream,Activity,"Class ID","Time & Day",Instructor(s),"Instructor(s) zID"'
			f.write(header)

			# iterate over all the classes
			for stream in project_list:
				s = project_list[stream]

				for clas in s['classes']:
					# for each class, get all instructors
					instructors = [] 
					
					for iid in clas['instructors']:
						if (iid in self.user_stafflist):
							instructors.append(self.user_stafflist[iid].name)

					f.write(f'\n{stream},"{clas["name"]}",{clas["class_id"]},"{clas["description"]}","{", ".join(instructors)}","{", ".join(clas["instructors"])}"')

		self.logger.log(f'Exported class list to {output_path}\n\n')

	def get_team (self, team_id, get_channels=False):
		""" Get basic team info """
		self.ensure_connected()

		response = self.process.run_command(
			f'Get-Team -GroupId {team_id}',
			convert_json = True
		)

		if (get_channels):
			response['channels'] = self.get_channels(team_id)

		self.logger.log(f'Got info on Team named {response["DisplayName"]} ({team_id})')
		
		return response

	def create_team (self, name, description='', visibility='Private', template=None, info=''):
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
			self.logger.log(f'Failed to create {visibility.lower()} team {name} (response: {response_group_id}) ({info=})', 'ERROR')
		else:
			self.logger.log(f'Created {visibility.lower()} team {name} ({response_group_id}) ({info=})')

			return response_group_id

	def set_team (self, team_id, new_name=None, description=None):
		""" adjust name and description of an existing team """
		self.ensure_connected()

		# only continue if there is something to adjust
		if (new_name is None and description is None):
			return False

		name = ''
		if (new_name != None):
			name = f' -DisplayName "{new_name}"'

		desc = ''
		if (description != None):
			desc = f' -Description "{description}"'

		# edit team
		response = self.process.run_command(
			f'Set-Team -GroupId {team_id}{name}{desc}'
		)

		# TODO parse response
		#Set-Team: Team not found

		self.logger.log(f'Edited Team {team_id}')

	def set_team_picture (self, team_id, image_path):
		""" update the team picture """
		self.ensure_connected()

		if (os.path.exists(image_path) is False):
			self.logger.log(f'Image to set Team picture for {team_id} does not exist', 'ERROR')
			return False

		# edit team
		response = self.process.run_command(
			f'Set-TeamPicture -GroupId {team_id} -ImagePath {image_path}'
		)

		# TODO parse response

		self.logger.log(f'Updated Team picture for {team_id}')

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
		
		# Get-TeamChannelUser: Error occurred while executing 
		# Code: Forbidden

		# if channel not found, stop
		if (type(response) == 'str'):
			 # if (response.find('Team not found') != -1):
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

			# sometimes, returned user data may contain the 'nice' email address, not a user ID
			#   so instead of z1234567@ad.unsw.edu.au, we get f.somename@ad.unsw.edu.au
			#   if so, we'd need to do a lookup (f.somename -> z1234567) as sending commands and
			#   everything else still relies on user IDs being submitted
			if (not re.match('^z[\d]{7}$', userid)):
				# try stafflist first
				for uw in self.user_stafflist:
					if (self.user_stafflist[uw]['email'].replace('@ad.unsw.edu.au','') == userid):
						userid = uw
						break
				# then try the regular userlist
				for ul in self.user_list:
					if (self.user_list[ul]['email'].replace('@ad.unsw.edu.au','') == userid):
						userid = ul
						break

			# check userid again, if we haven't resolved the lookup, this user is skipped
			#   note that we won't be able to properly handle any user unknown to whichever source list
			#   was imported, which may hamper us in some ways
			if (not re.match('^z[\d]{7}$', userid)):
				self.logger.warning(f'Could not parse user id for {userid}')
				continue

			user_list[userid] = User(
				userid,     # zID
				d['Name'],  # name    
				'',         # unknown course code   
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
		""" Convenience function to remove a list of users in one go """
		for u in users:
			self.remove_user_from_team(team_id, u, role)

	def remove_user_from_team (self, team_id, user=User, role='Member'):
		""" Removing a user as role='Owner' keeps them as a team member """
		self.ensure_connected()

		# skip the uni-added service accounts
		if (user.id in self.exclusion_ids):
			return False

		response = self.process.run_command(
			f'Remove-TeamUser -GroupId {team_id} -User {user.id}@ad.unsw.edu.au -Role {role}'
		)

		success = True

		# TODO check response
		#Remove-TeamUser: Error occurred while executing 
		#Remove-TeamUser: Last owner cannot be removed from the team
		if (len(response) == 0):
			self.logger.info(f'Team {team_id}: Removed {user} as {role}')
		else:
			success = False
			self.logger.error(f'Team {team_id}: Could not remove {user} as {role}')

		return success

	def add_users_to_team (self, team_id, users=[User], role='Member'):
		""" Convenience function to add a list of users in one go """
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

		# TODO check response
		success = True
		#Request_ResourceNotFound
		if (len(response) == 0):
			self.logger.info(f'Team {team_id}: Added {user} as {role}')
		else:
			success = False
			self.logger.error(f'Team {team_id}: Could not add {user} as {role}')

		return success

	def update_team (self, team_id, desired_user_list, team_user_list=None, role='All', remove_allowed=True):
		""" Sync team membership by comparing `desired_user_list` with `channel_user_list` (latter will be fetched if not specified) """
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
				if (remove_allowed):
					response = self.remove_user_from_team(team_id, team_user_list[user_in_teams_list])
					
					if (response):
						count_removed += 1
				else:
					self.logger.info(f'Team {team_id}: Skipped removing {team_user_list[user_in_teams_list]} as {role}')
				
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

		self.logger.info(f'Updating team {team_id} complete (- {count_removed} / + {count_added})')

		return (count_removed, count_added)

	def get_channels (self, team_id, channel_type=None):
		""" Get all the channels for a team """
		self.ensure_connected()

		mtype = ''
		if (channel_type != None):
			mtype = f' -MembershipType {channel_type}'  # Standard|Private

		# create channel
		response = self.process.run_command(
			f'Get-TeamChannel -GroupId {team_id}{mtype}',
			convert_json = True
		)

		all_channels = {}

		# single channel response isn't given as a list, just the channel dict is returned, so wrap in list
		if (isinstance(response, dict)):
			response = [response]

		for ch in response:
			all_channels[ ch['DisplayName'] ] = ch

		self.logger.info(f'Got {len(all_channels)} channels in Team {team_id}')

		return all_channels

	def create_channel (self, team_id, channel_name, channel_type='Standard', description=None):
		""" Create a new channel in a team with the specific name and type """
		self.ensure_connected()

		desc = ''
		if (description != None):
			desc = f' -Description "{description}"'

		# ensure channel type is correctly fed into command
		ctype = channel_type.lower()
		if (ctype == 'private'):
			ctype = 'Private'
		else:
			ctype = 'Standard'

		# create channel
		response = self.process.run_command(
			f'New-TeamChannel -GroupId {team_id} -DisplayName "{channel_name}" -MembershipType {ctype}{desc}',
			convert_json = True
		)

		# parse response
		if (response.find('Error occurred while executing') == -1):
			self.logger.info(f'Created channel {channel_name} in Team {team_id}')
		else:
			reason = 'unknown reason'
			if (response.find('Channel name already existed') != -1):
				reason = 'Channel name already existed'

			self.logger.error(f'Could not create channel {channel_name} in Team {team_id} ({reason})')

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

		self.logger.info(f'Edited channel {channel_name} in Team {team_id}')

	def get_channels_user_list (self, channels_list, role='All'):
		""" TODO untested and unused at the moment """
		channels_user_lists = {}
		for ch in channels_list:
			channels_user_lists[ch.name] = self.get_channel_user_list(ch.team_id, ch.name, role=role)
		return channels_user_lists

	def get_channel_user_list (self, team_id, channel_name, role='All'):
		""" Get list of current users in channel, and return a dict with user ids as the keys """
		self.ensure_connected()

		# add filter if required
		role_filter = ''
		if (role != 'All'):
			role_filter = f' -Role {role}'

		response = self.process.run_command(
			f'Get-TeamChannelUser -GroupId {team_id} -DisplayName "{channel_name}"{role_filter}',
			convert_json = True
		)

		# TODO parse response
		if (type(response) == 'str'):
			# if (response.find('Channel not found') != -1):
			# 	pass
			# elif: (response.find('Forbidden') != -1):
			# 	pass
			self.logger.error(f'Channel {channel_name}: Could not get user list')
			return False
		else:
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
			# TODO disable after some tries due to a bug in PS module
			# if (self.user_channel_bug_counter > 5):
			# 	self.logger.warning(f'Skipped adding {role} status for {user} due to PS module bug')
			# else:
			response = self.process.run_command(
				f'Add-TeamChannelUser -GroupId {team_id} -DisplayName "{channel_name}" -User {user.id}@ad.unsw.edu.au -Role {role}'
			)

		# parse response
		success = True
		# empty response is sign of success, so check for that
		if (len(response) == 0):
			self.logger.info(f'Channel {channel_name}: Added {user} as {role}')
		else:
			if (response.find('Failed to find the user on the channel roster')):
				self.user_channel_bug_counter += 1
			# if (response.find('User is not found in the team.') != -1 or response.find('Could not find member.') != -1 or response.find('Authorization_RequestDenied') !=-1):
			"""
			Add-TeamChannelUser: Error occurred while executing 
			Code: BadRequest
			Message: Invalid OData type specified: "Microsoft.Teams.Core.aadUserConversationMember"
			HttpStatusCode: BadRequest
			"""
			success = False
			self.logger.error(f'Channel {channel_name}: Could not add {user} as {role}')

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
		if (len(response) == 0):
			self.logger.info(f'Channel {channel_name}: Removed {user} as {role}')
		else:
			success = False
			print(response)
			self.logger.error(f'Channel {channel_name}: Could not remove {user} as {role}')
		
		# TODO parse response
		# Remove-TeamChannelUser: Error occurred while executing 
		# Code: NotFound
		# Message: Not Found
		# InnerError:
		# RequestId: 55982b3c-1319-4614-97bf-68e67ea94f90
		# DateTimeStamp: 2020-09-19T23:46:30
		# HttpStatusCode: NotFound
		
		return success

	def update_channel (self, team_id, channel_name, desired_user_list, channel_user_list=None, role='All', remove_allowed=True):
		""" Sync channel membership by comparing `desired_user_list` with `channel_user_list` (latter will be fetched if not specified) """
		self.logger.info(f"Updating channel {channel_name} ({len(desired_user_list)} enrolments)")

		count_removed = 0
		count_added   = 0

		desired_user_list = self.ensure_dict(desired_user_list)
		channel_user_list = self.ensure_dict(channel_user_list)

		if (channel_user_list is None):
			# get the team user list
			channel_user_list = self.get_channel_user_list(team_id, channel_name, role)

		# check current teams list against desired list
		#	remove any not on desired list (but check against stafflist, those are save from deletion)
		for user_in_teams_list in channel_user_list:
			# skip the uni-added service accounts
			if (user_in_teams_list in self.exclusion_ids): 
				continue

			if (user_in_teams_list not in desired_user_list and user_in_teams_list not in self.user_stafflist):
				if (remove_allowed):
					# no role is indicated, so removal should remove the user rather than demote them from owner to member
					response = self.remove_user_from_channel(team_id, channel_name, channel_user_list[user_in_teams_list])
					
					if (response):
						count_removed += 1
				else:
					self.logger.info(f'Channel {channel_name}: Skipping removing {channel_user_list[user_in_teams_list]} as {role}')
				
		# add any not in teams list but on desired list
		for user_in_desired_list in desired_user_list:
			if (user_in_desired_list not in channel_user_list):
				# manage by role
				if (role == 'All'):
					# follow User role
					response = self.add_user_to_channel(team_id, channel_name, desired_user_list[user_in_desired_list], role=desired_user_list[user_in_desired_list].role())
				else:
					# follow the generic role indicated
					response = self.add_user_to_channel(team_id, channel_name, desired_user_list[user_in_desired_list], role)
				
				if (response):
					count_added += 1

		self.logger.info(f'Updating channel {channel_name} complete (- {count_removed} / + {count_added})')

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

	def convenience_get_stream_owners (self, stream_name, stream_data, existing_owners=[]):
		"""
		Get all owners based on user list and stream data
		"""
		owners = self.ensure_dict(existing_owners)

		# find by groupname in user list
		owners_in_user_list = self.find_users('group', f'Staff {stream_name}', self.user_stafflist, return_type='dict')

		for ol in owners_in_user_list:
			if (ol not in owners):
				owners[ol] = owners_in_user_list[ol]

		# use stream data to fill in gaps (particularly handy if people are missing from userlist)
		for co in stream_data['coordinators']:
			if (co not in owners):
				if (co in self.user_stafflist):
					owners[co] = self.user_stafflist[co]
				elif (co in self.user_list):
					owners[co] = self.user_list[co]
				else:
					# add a dummy user
					c = User(co, '~~unknown~~', [], [], [], '', True)
					owners[co] = c

		for oo in stream_data['other_owners']:
			if (oo not in owners):
				if (oo in self.user_stafflist):
					owners[oo] = self.user_stafflist[oo]
				else:
					# add a dummy user
					o = User(oo, '~~unknown~~', [], [], [], '', True)
					owners[oo] = o

		for clas in stream_data['classes']:
			for demonstrator_id in clas['instructors']:
				if (demonstrator_id not in owners):
					if (demonstrator_id in self.user_stafflist):
						owners[demonstrator_id] =self.user_stafflist[demonstrator_id]
					else:
						# add a dummy user
						d = User(demonstrator_id, '~~unknown~~', [], [], [], '', True)
						owners[demonstrator_id] = d

		return self.ensure_list(owners)

	def convenience_create_class_channels (self, stream_data, current_channels):
		""" Create class channels based on given stream data """
		for clas in stream_data['classes']:
			if (clas['channel']):
				channel_name = f'{clas["name"]}_{clas["class_id"]}'

				if (channel_name in current_channels):
					# check if type is correct - if not, warn (mismatch can't be resolved without recreating channel)
					current_type = current_channels[channel_name]['MembershipType'].lower().replace('standard','public')

					if (current_type != clas['channel']):
						self.logger.error(f"Channel {channel_name} in {stream_data['team_id']}: Wrong membership type: not {clas['channel']}")
					
					# check if description is correct - if not, update
					if (current_channels[channel_name]['Description'] != clas['description']):
						self.set_channel(stream_data['team_id'], channel_name, description=clas['description'])
				else:
					# create channel
					ctype = 'Standard'
					if (clas['channel'] == 'private'):
						ctype = 'Private'

					self.create_channel(stream_data['team_id'], channel_name, ctype, description=clas['description'])

	def convenience_sync_class_channels (self, stream_data, owners, sync_staff=True, sync_students=True, remove_staff_allowed=True, remove_students_allowed=True):
		""" Synchronise stream class channel membership against a given user list """
		for clas in stream_data['classes']:
			# only need to sync private channels as those have a memberlist separate from main team
			if (clas['channel'] and clas['channel'] == 'private'):
				channel_name = f'{clas["name"]}_{clas["class_id"]}'

				# update owners
				if (sync_staff):
					self.update_channel(stream_data['team_id'], channel_name, owners, role='Owner', remove_allowed=remove_staff_allowed)
				
				# update students
				if (sync_students):
					class_students = self.find_users('class id', clas['class_id'], return_type='dict')

					self.update_channel(stream_data['team_id'], channel_name, class_students, role='Member', remove_allowed=remove_students_allowed)

	def convenience_sync_channels (self, stream_data, sync_staff=True, sync_students=True, remove_staff_allowed=True, remove_students_allowed=True):
		"""
		Convenience method to sync channels within a stream
		TODO - doesn't respect input parameters very well...
		     - could be more generic for broader use
		"""
		for channel in stream_data['channels']:
			if (channel['channel'] == 'private'):
				# work through owner and member configuration
				for role in ['Owner','Member']:
					role_name = f'{role.lower()}s' # 'owners' or 'members'

					if (role_name in channel):
						# defaults
						users          = self.user_list
						remove_allowed = remove_students_allowed
						
						# implement user list changes and search filter
						user_list    = None
						if ('list' in channel[role_name]):
							user_list = channel[role_name]['list'].lower()

							# handle any special cases
							if (user_list == 'stream_owners'):
								users     = stream_data['stream_owners']
								user_list = stream_data['stream_owners']
								remove_allowed = remove_staff_allowed
							# or handle general case
							elif ('staff' in user_list or 'owner' in user_list):
								users          = self.user_stafflist
								user_list      = self.user_stafflist
								remove_allowed = remove_staff_allowed

						filter_key   = None
						filter_terms = None
						if ('filter' in channel[role_name]):
							filter_key  = channel[role_name]['filter']
							filter_terms = channel[role_name]['filter_terms']
						
							users = self.find_users(filter_key, filter_terms, list_to_search=user_list, return_type='dict')
						
						# do actual update
						self.update_channel(stream_data['team_id'], channel['name'], users, role=role, remove_allowed=remove_allowed)

	def convenience_course_stream_update (self, team_name, stream_name, stream_data, course_owners='', include_staff=True, sync_staff=True, sync_students=True, remove_staff_allowed=True, remove_students_allowed=True, set_team_picture=False):
		""" Default stream update method, suitable for most courses """

		# ---- find stream owners ----
		course_owners  = self.find_users('group', f'Staff {course_owners}', self.user_stafflist)
		stream_owners = []
		# initially, we may exclude staff to give time for early setup
		if (include_staff):
			stream_owners = self.convenience_get_stream_owners(stream_name, stream_data, course_owners)
		else:
			stream_owners = course_owners
		# store for later use
		stream_data['stream_owners'] = stream_owners

		# ---- get basic team info ----
		team_info         = self.get_team(stream_data['team_id'], get_channels=True)

		# ---- set appearance ----
		team_name    = f'{my_course_code} {stream} - {my_year} T{my_term}'
		description  = f'Teaching Team for {team_name}'

		if (team_info['DisplayName'] != team_name or team_info['Description'] != description):
			self.set_team(stream_data['team_id'], new_name=team_name, description=description)

		# set Team picture
		if (set_team_picture):
			# TODO remove hardcoded path
			self.set_team_picture(stream_data['team_id'], f'../Logos/{my_course_code}-{stream.lower()}.png')

		# ---- create channels ----
		# class channels
		self.convenience_create_class_channels(stream_data, team_info['channels'])

		# additional channels
		for channel in stream_data['channels']:
			if (channel['name'] not in team_info['channels'] and channel['channel']):
				self.create_channel(stream_data['team_id'], channel['name'], channel_type=channel['channel'], description=channel['description'])

		# ---- sync members ----
		if (sync_staff):
			# update team owners
			self.update_team(stream_data['team_id'], stream_owners, role='Owner', remove_allowed=remove_staff_allowed)

			# sync additional channels
			self.convenience_sync_channels(stream_data, sync_staff=sync_staff, sync_students=sync_students, remove_staff_allowed=remove_staff_allowed, remove_students_allowed=remove_students_allowed)

		# sync private class channels
		self.convenience_sync_class_channels(stream_data, stream_owners, sync_staff=sync_staff, sync_students=sync_students, remove_staff_allowed=remove_staff_allowed, remove_students_allowed=remove_students_allowed)

		return team_info


class MoodleBrowser:
	"""
	Reusable browser connection to Moodle
	Allows for reusing the same login session with multiple MoodleUpdater instances,
	so several courses can be handled without having to login for each of them.
	"""
	def __init__ (self, username, password, logger=None):
		self.browser   = None
		self.logged_in = False

		if (logger == None):
			self.logger = Logger()
		else:
			self.logger = logger

		self.login(username, password)

	def login (self, username, password):
		"""
		Logs in to single-sign on for Moodle (thus with Office 365 credentials)
		usually doesn't fail, so that's quite nice
		"""
		self.logger.info('Logging in to Moodle...')
		
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
		# TODO headless=True currently causes a crash...
		self.browser = Browser('firefox', profile_preferences=profile_preferences, headless=False)
		
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
			self.logger.info('Logged in to Moodle successfully.')
			self.logged_in = True
			return True
		
		# else
		self.logger.warning('Moodle login may have failed')
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


class MoodleUpdater:
	"""
	Class that enables a small number of repetitive operations on Moodle

	`course_id` is unique, look at the url on Moodle to find the id for the course
	"""
	def __init__ (self, course_id, username=None, password=None, browser=None, logger=None):
		self.course_id = course_id
		self.csv_file  = None
		self.logged_in = False

		if (logger == None):
			self.logger = Logger()
		else:
			self.logger = logger

		if (browser == None):
			self.browser          = MoodleBrowser(username, password, logger)
			self.browser_internal = True
		else:
			self.browser = browser
			self.browser_internal = False

		# convenience variable for short/more readable code
		self.b = self.browser.browser

	def close (self):
		if (self.browser_internal):
			self.browser.close()

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

	def get_users_csv (self, auto_confirm=True):
		"""
		Downloads the user list as csv export from Moodle

		Note that Moodle sets the filename and this script's browser instance can't control that.
		It also doesn't indicate when a download may have completed, so this requires manual confirmation,
		unless `auto_confirm` is set to `True` when it does a rudimentary file check and moves on.
		"""
		self.logger.info('Getting user data CSV file from Moodle...')
	
		# get all users on one page
		self.b.visit(f'https://moodle.telt.unsw.edu.au/user/index.php?id={self.course_id}&perpage=5000&selectall=1')
		# give extra time to let large page settle
		time.sleep(30)
		# check if the 'select all' checkbox is ticked (should be per the url but fails with slow/large courses)
		checkbox_el    = self.b.find_by_id('select-all-participants')
		checkbox_label = self.b.find_by_css('label[for=select-all-participants]')
		# .text says 'Deselect all' if it's checked; 'Select all' if unchecked
		if (checkbox_label.text != 'Deselect all'):
			checkbox_el.click()  # select it now
			time.sleep(5)        # can be slow with 1000+ users

		# find the course name
		course_name = self.b.find_by_tag('h1')[0].text
		filename    = course_name.lower().replace(' ','-').replace('&','-') + '.csv'

		# temporarily move the current file if it exists
		#   this prevents the new download to be renamed by the browser as file(1) to avoid overwriting it
		old_filename = filename.replace('.csv', '-old.csv')
		if (os.path.exists(filename)):
			os.rename(filename, old_filename)
		
		# select the export CSV option (which triggers a download)
		self.logger.info('Downloading user list as CSV...')
		el = self.b.find_by_id('formactionid')
		el.select('exportcsv.php')

		# it is assumed the file is now automatically downloaded to the current working folder
		#   however, there is no way of knowing the file has finished downloading
		#   so this needs some intervention...
		got_file = 'no'

		if (auto_confirm):
			# add some extra buffer to be sure download completed
			time.sleep(10)
			if (os.path.exists(filename)):
				got_file = 'yes'
		else:
			# manual confirmation
			Notifier.notify('Moodle csv download', 'Check download status and confirm')
			got_file = input('Downloaded file? [Y]es or [N]o: ').lower()

		# continue with downloaded file
		if ('y' in got_file):
			self.logger.info(f'Moodle user data downloaded to {filename}')

			# remove old file if it's there
			if (os.path.exists(old_filename)):
				os.remove(old_filename)

			self.csv_file = filename
			return filename
		else:
			# if unsuccessful we end up here...
			self.logger.error(f'Unable to download Moodle user data')

			# rename the old file to its former name
			if (os.path.exists(old_filename)):
				os.rename(old_filename, filename)

				return filename

	def get_grouping_data (self, output_path):
		"""
		Extracts grouping info and exports to csv.
		
		On importing user data, this data can be joined in to get grouping membership for users.
		"""
		self.logger.info('Getting grouping data from Moodle...')
		
		# go to grouping overview page
		self.b.visit(f'https://moodle.telt.unsw.edu.au/group/groupings.php?id={self.course_id}')

		time.sleep(5)

		# structure of the groupings table
		#<table class="generaltable">  <-- class occurs only once so it's unique
		#	<thead>
		#	<tbody>
		#		<tr>
		#			<td class=cell c0>grouping name</td>
		#			<td class=cell c1>group1, group2</td>

		# find the table
		table = self.b.find_by_css('table[class=generaltable]').first
		
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

		self.logger.info('Grouping data export complete.')

		return groups_dict

	def get_grades_csv (self):
		""" TODO not sure if I ever used/tested this """
		self.logger.info('Getting grades data CSV file from Moodle...')
		
		# go to grades download page (and just get all grades)
		self.b.visit(f'https://moodle.telt.unsw.edu.au/grade/export/txt/index.php?id={self.course_id}')

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
		"""
		Automates the groups auto-creation interface on Moodle.
		Useful if auto-creating groups based on changing enrolment data; this can make sure data is
		refreshed and accurate before doing other things.

		It assumes this is run manually at least once so we're certain the `grouping_name`, if set, indeed exists.
		"""
		self.logger.info(f'Auto-creating groups by {group_by_type}...')
		
		# go straight to the auto-create groups page for the course
		self.b.visit(f'https://moodle.telt.unsw.edu.au/group/autogroup.php?courseid={self.course_id}')
		
		# pick the grouping type
		group_type_el = self.b.find_by_id('id_groupby')
		group_type_el.select( group_by_type.lower().replace(' ', '') )

		if (grouping_name is not None):
			# make the grouping selection area visible
			grouping_field_el  = self.b.find_by_id('id_groupinghdr')
			grouping_header_el = grouping_field_el.first.find_by_tag('a')
			grouping_header_el.click()

			# select the option (make sure to pick the last one as it may occur more than once elsewhere on the page)
			# grouping_select_el = self.b.find_by_id('id_grouping')
			self.b.find_option_by_text( grouping_name ).last.click()
			# alt method: self.b.select(selection_box_element, desired_option)

		# submit the form
		self.b.find_by_id('id_submitbutton').click()

		# give additional time to settle
		time.sleep(5)

		self.logger.info('Auto-creating groups complete.')

	def add_gradebook_category (self, category_info={}):
		"""
		Ruin the gradebook by running this experimental method. If lucky, it adds a category.

		category_info is a dict {} with the following parameters:
		  name            : (required) String of text
		  aggregation     : (optional) String of text, must match option name in Moodle
		  id              : (optional) String of text
		  grade_max       : (optional) Number (can be int or float)
		  parent_category : (optional) String of text, must match existing category name
		  weight          : (optional) Float in range [0,1]
		"""
		self.logger.info(f'Adding the {category_info["name"]} gradebook category...')

		# go straight to add/edit gradebook category page
		self.b.visit(f'https://moodle.telt.unsw.edu.au/grade/edit/tree/category.php?courseid={self.course_id}')

		# give some time to settle
		time.sleep(10)

		# expand all panes to simplify later steps
		# expand_el = self.b.find_by_css('a[class=collapseexpand]')  # causes crash now...
		expand_el = self.b.links.find_by_text('Expand all')
		try:
			expand_el.click()
		except:
			pass  # skip if it does not exist, just means we've already expanded

		# set fields
		# category name
		if ('name' in category_info):
			self.b.find_by_css('input[id=id_fullname]').fill(category_info['name'])
		# aggregation method           
		if (category_info['aggregation']):
			self.b.find_option_by_text( category_info['aggregation'] ).first.click()
		# ID number
		if ('id' in category_info):
			self.b.find_by_css('input[id=id_grade_item_idnumber]').fill(category_info['id'])
		# max grade
		if ('grade_max' in category_info):
			self.b.find_by_css('input[id=id_grade_item_grademax]').fill(str(category_info['grade_max']))
		# parent category
		if ('parent_category' in category_info):
			self.b.find_option_by_text( category_info['parent_category'] ).first.click()

		save_button_el = self.b.find_by_id('id_submitbutton')
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
				continue_el = self.b.find_by_css('button[type=submit]')

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
			label_els          = self.b.find_by_css('label[class=accesshide]')
			
			for l in label_els:
				if (l.text == f"Extra credit value for {category_info['name']}"):
					category_weight_id = l['for']
					break  # found the right one, exit for loop early
			
			if (category_weight_id is not None):
				weight_el = self.b.find_by_css(f'input[id={category_weight_id}]')
				weight_el.fill(str(category_info['weight']))

				# submit changes
				self.b.find_by_css('input[value=Save\ changes]').click()

				time.sleep(5)

		self.logger.info(f'Added the {category_info["name"]} gradebook category.')

	def add_section (self, section_info={}):
		"""
		Add a section to Moodle

		section_info is a dict {} with the following parameters:
		  name         : (required) String of text
		  description  : (optional) String of text
		  restrictions : (optional) list of dicts, e.g. [{'group': 'some group'}, {'grouping': 'some grouping'}]
		  hidden       : (optional) True or False
		"""
		self.logger.info(f'Adding section named {section_info["name"]}...')

		# go to course main page 
		self.b.visit(f'https://moodle.telt.unsw.edu.au/course/view.php?id={self.course_id}')

		time.sleep(10)

		# first check if section already exists
		section_title_els = self.b.find_by_css('a.quickeditlink')
		for s_title in section_title_els:
			if (s_title.text == section_info['name']):
				self.logger.info(f'Section named {section_info["name"]} already exists. Skipped.')
				return

		# enable editing by clicking the right button
		buttons = self.b.find_by_css('button[type=submit]')
		for b in buttons:
			if (b.text == 'Turn editing on'):
				b.click()

				# let things settle
				time.sleep(15)
				
				break  # no need anymore to check other buttons
			elif (b.text == 'Turn editing off'):
				break  # we're in the editing mode already

		# add an empty section
		self.b.find_by_css('a[class=increase-sections]').click()
		# wait for page to reload
		time.sleep(10)

		# edit section
		section    = self.b.find_by_css('li.section').last
		section_id = section['aria-labelledby'].replace('sectionid-', '').replace('-title', '')
		self.b.visit(f'https://moodle.telt.unsw.edu.au/course/editsection.php?id={section_id}&sr=0')
		
		time.sleep(10)

		# expand all panes to simplify later steps
		expand_el = self.b.find_by_css('a[class=collapseexpand]')
		expand_el.click()

		# fill name
		if ('name' in section_info):
			# enable a custom name
			self.b.find_by_id('id_name_customize').click()

			self.b.find_by_id('id_name_value').fill(section_info['name'])
		# fill description
		if ('description' in section_info):
			self.b.find_by_id('id_summary_editor').fill(section_info['description'])
		
		# set access restrictions
		if ('restrictions' in section_info):
			for r in section_info['restrictions']:
				self.b.find_by_text('Add restriction...').click()
				time.sleep(1)

				if ('group' in r):
					self.b.find_by_id('availability_addrestriction_group').click()
					time.sleep(1)
					self.b.find_option_by_text(r['group']).first.click()
				elif ('grouping' in r):
					self.b.find_by_id('availability_addrestriction_grouping').click()
					time.sleep(1)
					self.b.find_option_by_text(r['grouping']).first.click()
				else:
					self.logger.error(f'Restriction type in {r} is not supported yet')
				time.sleep(1)

				# toggle 'hide otherwise' eye icon when desired (do so by default)
				availability_eye_el = self.b.find_by_css('a.availability-eye')
				availability_eye_el.last.click()

		# save changes
		self.b.find_by_id('id_submitbutton').click()

		# returning to main sectin view
		time.sleep(10)

		# set hidden state (must be done from section view)
		if ('hidden' in section_info and section_info['hidden'] == True):
			# first, toggle the edit popup to be visible, then click the hide button within
			edit_toggle_buttons = self.b.find_by_css('a.dropdown-toggle')
			edit_toggle_buttons.last.click()
			time.sleep(0.5)

			hide_section_button = self.b.find_by_text('Hide section')
			hide_section_button.last.click()
			time.sleep(5)

		self.logger.info(f'Added section named {section_info["name"]}.')

	def remove_section (self, section_name):
		""" Removes a section with the specified name """

		self.logger.info(f'Removing section named {section_name}.')

		# go to course main page 
		self.b.visit(f'https://moodle.telt.unsw.edu.au/course/view.php?id={self.course_id}')

		time.sleep(10)

		# enable editing by clicking the right button
		buttons = self.b.find_by_css('button[type=submit]')
		for b in buttons:
			if (b.text == 'Turn editing on'):
				b.click()

				# let things settle
				time.sleep(10)
				
				break  # no need anymore to check other buttons
			elif (b.text == 'Turn editing off'):
				break  # we're in the editing mode already

		# find sections
		sections = self.b.find_by_css('li.section.main')
		
		for section in sections:
			# first check if section exists
			section_title_els = section.find_by_css('a.quickeditlink')
			
			# if found, continue with deleting it
			if (section_title_els.first.text == section_name):
				# first, toggle the edit popup to be visible, then click the hide button within
				edit_toggle_buttons = section.find_by_css('a.dropdown-toggle')
				edit_toggle_buttons.last.click()
				time.sleep(0.5)

				delete_section_button = section.find_by_text('Delete section')
				delete_section_button.last.click()
				time.sleep(5)

				self.logger.info(f'Removed section named {section_name}.')
				return

		# else
		self.logger.info(f'Skipped section named {section_name}: does not exist.')

	def export_default_groups_list (self, project_list, tech_stream_list=None, replace_terms={}):
		"""
		Generates a csv file for importing into Moodle with basic group and grouping setup
		
		This code is quite specific to courses that run multiple internal projects and/or streams
		and likely not useful for simpler courses.
		"""
		
		output_path = self.csv_file.replace('.csv', '-groups.csv')

		with open(output_path, 'w') as fo:
			# write header
			fo.write('groupname,groupingname')

			fo.write(f'\n"Staff (DO NOT REMOVE)","Staff Grouping (All)"')

			for pname in project_list:
				p = project_list[pname]

				fo.write(f'\n"Staff {pname}","Staff Grouping (All)"')

				students_term = 'Students'
				if (replace_terms['Students']):
					students_term = replace_terms['Students']

				student_term = 'Student'
				if (replace_terms['Student']):
					students_term = replace_terms['Student']

				if ('main_class_id' in p):
					fo.write(f'\n"{p["main_class_id"]}","{students_term} Grouping - {pname}"')
					fo.write(f'\n"{p["main_class_id"]}","{students_term} Grouping (All)"')
				else:
					fo.write(f'\n"DUMMY GROUP","{students_term} Grouping - {pname}"')
					fo.write(f'\n"DUMMY GROUP","{students_term} Grouping (All)"')
				
				fo.write(f'\n"DUMMY GROUP","{student_term} Teams - {pname}"')
				fo.write(f'\n"DUMMY GROUP","{student_term} Teams (All)"')

			if (tech_stream_list is not None):
				for tname in tech_stream_list:
					t = tech_stream_list[tname]

					fo.write(f'\n"Staff {tname}","Staff Grouping (All)"')

					fo.write(f'\n"Technical Stream Group - {tname} (Online)","Technical Stream Grouping - {tname}"')
					fo.write(f'\n"Technical Stream Group - {tname} (OnCampus)","Technical Stream Grouping - {tname}"')
					fo.write(f'\n"Technical Stream Group - {tname} (Online)","Technical Stream Grouping - All"')
					fo.write(f'\n"Technical Stream Group - {tname} (OnCampus)","Technical Stream Grouping - All"')

			self.logger.info(f'\nExported groups list to {output_path}\n\n')

	def get_workshop_grades (self, assessment_id):
		""" EXPERIMENTAL Download grades from a UNSW Workshop tool """
		self.logger.info(f'\nDownloading workshop grades for {assessment_id}')

		self.b.visit(f'https://moodle.telt.unsw.edu.au/mod/workshep/view.php?id={assessment_id}')
		time.sleep(10)

		# get table data
		table      = self.b.find_by_css('table.grading-report')
		table_rows = table.find_by_tag('tbody').find_by_tag('tr')

		submission_data = []

		for row in table_rows:
			try:
				d = {
					'name'      : row.find_by_css('td.participant').text,
					'submission': row.find_by_css('td.submission').find_by_tag('a')['href'],
					'grades'    : []
				}

				submission_data.append(d)
				print(d['name'])
			except:  #splinter.exceptions.ElementDoesNotExist as e
				pass

			# if a user receives multiple grades, those are put into subsequent rows
			#   those additional rows miss the participant and submission data, and only carry grade data
			#   so if the above try block fails, we got the second type and just add the parsed grade to the last item in data
			# TODO while this bit works, it's painfully slow...
			receivedgrade = row.find_by_css('td.receivedgrade')  # example: '- (-)<Jimmy Liu'

			if (len(receivedgrade) > 0 and receivedgrade.text != '-'):  # <- no markers assigned
				grade  = receivedgrade.find_by_css('span.grade').text
				marker = receivedgrade.find_by_css('span.fullname').text

				grade_data = {
					'grade' : grade,
					'marker': marker
				}
				submission_data[-1]['grades'].append(grade_data)

		# export to csv file
		output_path = f'workshop-{assessment_id}.csv'
		# output_path = self.csv_file.replace('.csv', f'-workshop-{assessment_id}.csv')

		with open(output_path, 'w') as f:
			# header
			f.write('"Student name","Student zID",Submission,Grade,Marker,"Marker zID"')

			for sub in submission_data:
				# by focusing only on grades, any entry without grades is skipped
				#   note: this means that students without a marker allocated may be skipped
				for grade in sub['grades']:
					f.write(f'\n"{sub["name"]}",-,{sub["submission"]},{grade["grade"]},"{grade["marker"]}",-')

		self.logger.info(f'Exported workshop grades for {assessment_id} to {output_path}')


class LMUpdater:
	"""
	Class that enables a small number of repetitive operations on the Learning Management system via myUNSW

	Not functional at the moment -> more an elaborate set of notes for future work if I feel it's worth the time.
	"""
	def __init__ (self, course_name, course_term, username, password):
		self.course_name = course_name
		self.course_term = course_term
		self.logged_in = False

		self.login(username, password)

	def login (self, username, password):
		"""
		Logs in to myUNSW
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

	def get_class_roster (self, term, course_code):
		"""
		UNFINISHED. Downloads the class roster for the course.
		Data may be useful in addition to what Moodle provides as it contains degree program.
		"""

		#visit('https://my.unsw.edu.au/academic/roster/reset.xml')
		
		# select right term
		#select.form-control name="term"
		#  optons value="5219" text "Term 3 2021"

		# pick right course
		#3rd table > tbody
		# each tr is one course
		#1st td is course_code
		#if (td_els.first.text == course_code):
		#	td_els.last.input_el.click()
		
		# move to next page, give time to settle
		time.sleep(10)

		# td.formBody
		# 2nd table element
		# get tbody
		# 1st tr > list of td.tableHeading text is column names
		# remaining trs are data

		# export to csv file
		# needs predicatable filename

		# TODO
		# if available, use this info in import_user in TeamsUpdater


# -----------------------------------------------------------------------------


if __name__ == '__main__':
	"""
	This is a default use case
	Best practice is to create a new script file, import this script's classes there, and make it work for your use case.
	"""

	# path to Moodle-exported CSV file (default given here, override with a suitable path)
	my_path = 'desn2000-engineering-design---professional-practice---2020-t3.csv'
	
	# get login info
	login = LoginData()

	# get data from Moodle
	moodle_course_id = 54605

	# do stuff on Moodle
	with MoodleUpdater(moodle_course_id, login.username, login.password) as mu:
		my_path = mu.get_users_csv()

	# basic operation by default
	with TeamsUpdater(my_path, username=login.username, password=login.password) as tu:
		# import data first - later steps build on this
		tu.import_user_list()
		
		# do other things
		# ...
