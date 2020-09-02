#!/usr/bin/python3

import pandas as pd

student_data_path = 'desn2000-engineering-design-2---t2-2020.csv'

groups_of_interest = [
	'SENG_TUT_F15C_9811_ Team 2',
	'SENG_TUT_F12C_9807_ Team 5',
	'ELEC_TUT_H14A_9814_ Team 14',
	'ELEC_TUT_W11A_9825_ Team 10',
	'SENG_TUT_F12D_9808_ Team 2',
	'SENG_TUT_F12D_9808_ Team 3',
	'ELEC_TUT_H14A_9814_ Team 11',
	'ELEC_TUT_H14A_9814_ Team 5',
	'COMP_LAB_T12A_9821_ Team 5',
	'COMP_LAB_T12A_9821_ Team 7'
]

dataframe = pd.read_csv(student_data_path)

print('Using data from: {}'.format(student_data_path))
print('Imported data on {} students.\n\n'.format(len(dataframe.index)))

# do a quick class ID check
with open('teams.txt', 'w') as f:
	for g in groups_of_interest:
		print('\n' + g)
		f.write('\n\n' + g + '\n')

		for index, student in dataframe.iterrows():
			if student['Group4'] == g or student['Group6'] == g:
				full = '{fname} {surname} <{email}>'.format(
					fname = student['First name'],
					surname = student['Surname'],
					email = student['Email address']
				)

				print(full)
				f.write(full + '\n')
