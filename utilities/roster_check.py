import csv

with open('DESN2000-2021-T3-class-roster.csv') as fs:
	filereader = csv.DictReader(fs)

	# for every user (a row in csv file), parse data
	for user in filereader:
		#ID	Title	Name	Program	Plans	Stage	CRS	LAB	LE1	LE2	TUT
		zid   = 'z' + user['ID']
		name  = user['Name']
		plans = user['Plans'].lower()  # examples: "MTRNAH3707", "CEICAH3762, CHEMB13762" 
		stage = user['Stage'].lower()
		CRS   = user['CRS'].lower()
		LE2   = user['LE2'].lower()    # examples: "MEC2", "SPR2"

		# Term 2
		if ('elec' in LE2):
			if ('elecah' in plans or 'elecbh' in plans or 'elecch' in plans or 'teleah' in plans or 'compbh' in plans):
				pass
			else:
				print(f'{name:25}, {zid}, STREAM: {LE2}, PLANS: {plans:20}')

		if ('sen' in LE2):
			if ('sengah' in plans):
				pass
			else:
				print(f'{name:25}, {zid}, STREAM: {LE2}, PLANS: {plans:20}')

		if ('bin' in LE2):
			if ('binfah' in plans):
				pass
			else:
				print(f'{name:25}, {zid}, STREAM: {LE2}, PLANS: {plans:20}')

		if ('civ' in LE2):
			if ('cvenah' in plans or 'cvenbh' in plans or 'gmatdh' in plans):
				pass
			else:
				print(f'{name:25}, {zid}, STREAM: {LE2}, PLANS: {plans:20}')

		# Term 3
		if ('mec' in LE2):
			if ('mtrnah' in plans or 'aeroah' in plans or 'mechah' in plans or 'manfbh' in plans):
				pass
			else:
				print(f'{name:25}, {zid}, STREAM: {LE2}, PLANS: {plans:20}')

		if ('che' in LE2):
			if ('ceicah' in plans or 'ceicdh' in plans):
				pass
			else:
				print(f'{name:25}, {zid}, STREAM: {LE2}, PLANS: {plans:20}')

		if ('ptr' in LE2):
			if ('petrah' in plans):
				pass
			else:
				print(f'{name:25}, {zid}, STREAM: {LE2}, PLANS: {plans:20}')

		if ('min' in LE2):
			if ('mineah' in plans):
				pass
			else:
				print(f'{name:25}, {zid}, STREAM: {LE2}, PLANS: {plans:20}')

		if ('spr' in LE2):
			if ('solaah' in plans or 'solabh' in plans):
				pass
			else:
				print(f'{name:25}, {zid}, STREAM: {LE2}, PLANS: {plans:20}')


# idea for integration into teams_updater
"""
students = self.find_users('class id', stream_data['main_class_id'])

for stu in students:
	for plan in stu.plans:
		if (plan.lower() in stream_data['plans_allowed']):
			pass  # all good, no need to do anything
		else:
			# report
			print(f'{name:25},{zid},{plans:20},{LE2}')
"""
