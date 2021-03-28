import csv

with open('engg1000-engineering-design---2021-t1.csv') as fs:
	filereader = csv.DictReader(fs)

	print('Username')
	for row in filereader:
		print(row['Username'])