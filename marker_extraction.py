import csv
from random import randint

filepath = 'desn2000-engineering-design-and-professional-practice---2021-t3-students.csv'

with open(filepath) as fs:
	filereader = csv.DictReader(fs)

	with open(filepath.replace('-students','-allocations'), 'w') as fo:
		# header
		fo.write('Index,Username,"Student name",School,Marker')

		# for every user (a row in csv file), parse data
		for index, user in enumerate(filereader):

			marker = user['School demonstrator zID'].split(', ')

			if (len(marker) > 1):
				marker = marker[randint(0,len(marker)-1)]
			else:
				marker = marker[0]
			
			print(index,user['Student zID'],marker)
			fo.write(f"\n{index},{user['Student zID']},{user['Student name']},{user['School']},{marker}")