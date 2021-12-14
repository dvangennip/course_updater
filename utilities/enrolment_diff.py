from teams_updater import User
import csv
import sys

def import_user_data (path):
	user_list = {}

	with open(path) as fs:
		filereader = csv.DictReader(fs)

		for row in filereader:
			class_ids = []
			if (row['Class ID'] != '-'):
				class_ids = list(map(int, row['Class ID'].split(',')))
			
			groups = []
			for n in range(1,50):
				g = row[f'Group{n}']
				if (g is not None  and type(g) is str and len(g) > 0):
					groups.append(g)

			user = User(
				row['Username'],
				row['First name'] + ' ' + row['Surname'],
				'unknown_course_code',
				class_ids,
				groups
			)
			user_list[user.id] = user

	return user_list

def main ():
	if (len(sys.argv) == 3):
		list_one = import_user_data(sys.argv[1])
		list_two = import_user_data(sys.argv[2])

		count_unenrolled     = 0
		count_enrolled       = 0
		count_enrolled_staff = 0

		print('\nDifference between input lists:\n')

		for s1 in list_one:
			if list_one[s1].id not in list_two:
				print(f'Unenrolled: {list_one[s1]}\t\t\t{list_one[s1].groups}')
				count_unenrolled += 1

		print('\n-----------------------\n')

		for s2 in list_two:
			if list_two[s2].id not in list_one:
				print(f'New enrolment: {list_two[s2]}\t\t\t{list_two[s2].groups}')
				count_enrolled += 1

				if len(list_two[s2].class_ids) == 0 or list_two[s2].in_group('Staff (DO NOT REMOVE)'):
					count_enrolled_staff += 1

		print('\n-----------------------\n')
		print(f'Total unenrolled: {count_unenrolled:>4}')
		print(f'Total enrolled  : {count_enrolled:>4}\t({count_enrolled - count_enrolled_staff} students, {count_enrolled_staff} staff)')

	else:
		print('Usage: enrolment_diff.py file_one.csv file_two.csv')

if __name__ == '__main__':
	main()
