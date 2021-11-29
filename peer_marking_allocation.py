#!/usr/bin/python3

"""
pseudo-code for a script that could generate peer marking allocations
based on a given set of rules

intended use case: peer marking allocations for ENGG1000 EDP
benefit: faster than (semi) manual methods, correct output given correct input
"""

submissions_list = gather all submissions

# allocate x submissions to each student
for student in students:
	# check if student is in a project, otherwise skip to next one
	if (student is in a project is False):
		continue

	# 3x allocate a submission to mark
	max_allocations = 3
	allocations     = []

	# per pick:
	while (len(allocations) < max_allocations):
		pick 1 submission at random
		--- or pick 1 team within

		# checks
		#1. is this the student's own team?
		#   yes -> pick another, no -> we're good 
		if (student in submission team):
			continue

		#2. is it within the same project?
		#   yes -> we're good, no -> pick another
		if (submission not in same project as student):
			continue
		
		#3. is it within the same mentor group?
		#   yes -> pick another, no -> we're good
		if (student mentor equals submission team mentor):
			continue

		# pick this submission
		allocations.append(this_one)

# for each submission, gather all students allocated to it
for submission in submissions:
	list = find all students who have been allocated to this submission

	print submission name/id + list