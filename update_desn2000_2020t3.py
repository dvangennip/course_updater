from teams_updater import ClassItem, User, TeamsUpdater

my_path = 'desn2000-engineering-design---professional-practice---2020-t3.csv'

# list of ClassItem instances
my_classes_list = [
	# ClassItem(1112,  'Demonstrators',  '458b02e9-dea0-4f74-8e09-93e95f93b473', 'DESN2000_2020T3_CVEN'),
	ClassItem(9621,  'TUT_T12A_9621',  '458b02e9-dea0-4f74-8e09-93e95f93b473', 'DESN2000_2020T3_CVEN'),
	ClassItem(9622,  'TUT_T14A_9622',  '458b02e9-dea0-4f74-8e09-93e95f93b473', 'DESN2000_2020T3_CVEN'),
	ClassItem(9623,  'TUT_T14B_9623',  '458b02e9-dea0-4f74-8e09-93e95f93b473', 'DESN2000_2020T3_CVEN'),
	ClassItem(9629,  'TUT_T16F_9629',  '458b02e9-dea0-4f74-8e09-93e95f93b473', 'DESN2000_2020T3_CVEN'),
	#ClassItem(9635,  'TUT_W14C_9635',  '458b02e9-dea0-4f74-8e09-93e95f93b473', 'DESN2000_2020T3_CVEN'),
	ClassItem(9636,  'TUT_W14D_9636',  '458b02e9-dea0-4f74-8e09-93e95f93b473', 'DESN2000_2020T3_CVEN'),
	ClassItem(9637,  'TUT_W14E_9637',  '458b02e9-dea0-4f74-8e09-93e95f93b473', 'DESN2000_2020T3_CVEN'),
	ClassItem(9641,  'TUT_W16D_9641',  '458b02e9-dea0-4f74-8e09-93e95f93b473', 'DESN2000_2020T3_CVEN'),
	ClassItem(9642,  'TUT_W16E_9642',  '458b02e9-dea0-4f74-8e09-93e95f93b473', 'DESN2000_2020T3_CVEN'),
	ClassItem(9643,  'TUT_W16F_9643',  '458b02e9-dea0-4f74-8e09-93e95f93b473', 'DESN2000_2020T3_CVEN'),

	# ClassItem(1111,  'Demonstrators',  'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH'),
	ClassItem(9614,  'TUT_H11A_9614',  'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH'),
	ClassItem(9615,  'TUT_H11B_9615',  'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH'),
	ClassItem(9617,  'TUT_H16A_9617',  'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH'),
	#ClassItem(9618,  'TUT_H16B_9618',  'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH'),
	ClassItem(9624,  'TUT_T16A_9624',  'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH'),
	ClassItem(9625,  'TUT_T16B_9625',  'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH'),
	ClassItem(9626,  'TUT_T16C_9626',  'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH'),
	ClassItem(9627,  'TUT_T16D_9627',  'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH'),
	ClassItem(9628,  'TUT_T16E_9628',  'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH'),
	ClassItem(10441, 'TUT_T16G_10441', 'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH'),
	ClassItem(10505, 'TUT_T16H_10505', 'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH'),
	ClassItem(9630,  'TUT_W09A_9630',  'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH'),
	ClassItem(9631,  'TUT_W09B_9631',  'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH'),
	ClassItem(9632,  'TUT_W11A_9632',  'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH'),
	ClassItem(9633,  'TUT_W14A_9633',  'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH'),
	ClassItem(9634,  'TUT_W14B_9634',  'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH'),
	ClassItem(9638,  'TUT_W16A_9638',  'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH'),
	ClassItem(9639,  'TUT_W16B_9639',  'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH'),
	ClassItem(9640,  'TUT_W16C_9640',  'facaca51-fc7e-4263-ae05-ffe39ba616e3', 'DESN2000_2020T3_MECH')
]

# list of User instances
my_user_whitelist = [
	User('z5159930', 'Andre Yiu',                  True, 'DESN2000_2020T3_CVEN'),
	User('z5092321', 'Sheila Sun',                 True, 'DESN2000_2020T3_CVEN'),
	User('z5209990', 'Holly Daniel',               True, 'DESN2000_2020T3_CVEN'),
	User('z5061476', 'Jason Wang',                 True, 'DESN2000_2020T3_CVEN'),
	User('z5061779', 'Lauren Bricknell',           True, 'DESN2000_2020T3_CVEN'),
	User('z5160122', 'Profita Chesda Keo',         True, 'DESN2000_2020T3_CVEN'),
	User('z5142017', 'Christine Sun',              True, 'DESN2000_2020T3_CVEN'),
	User('z5213374', 'Jagachchandarr Sekar Uthra', True, 'DESN2000_2020T3_CVEN'),
	User('z5113715', 'Tamara Neil',                True, 'DESN2000_2020T3_MECH'),
	User('z5061445', 'Matt Brand',                 True, 'DESN2000_2020T3_MECH'),
	User('z5116763', 'Jacqueline Orme',            True, 'DESN2000_2020T3_MECH'),
	User('z5163178', 'Shantanu Kumthekar',         True, 'DESN2000_2020T3_MECH'),
	User('z5116929', 'John Taglini',               True, 'DESN2000_2020T3_MECH'),
	User('z5208699', 'Elora Croaker',              True, 'DESN2000_2020T3_MECH'),
	User('z5214163', 'Thaveesha Piyasiri',         True, 'DESN2000_2020T3_MECH'),
	User('z5113875', 'Rachael Sharp',              True, 'DESN2000_2020T3_MECH'),
	User('z5061365', 'Garen Douzian',              True, 'DESN2000_2020T3_MECH'),
	User('z5112867', 'Courtney Morris',            True, 'DESN2000_2020T3_MECH'),
	User('z5157644', 'Yvonne Liaw',                True, 'DESN2000_2020T3_MECH'),
	User('z5162095', 'Rawan Abdo',                 True, 'DESN2000_2020T3_MECH')
]

if __name__ == '__main__':
	with TeamsUpdater(my_path, my_classes_list, my_user_whitelist) as tu:
		# tu.connect()

		tu.import_user_list()
		# tu.get_channels_user_list()

		# create channels - use step only when necessary
		# tu.create_channels(owners=ows)

		# add people to a team
		# cven_demos = tu.find_users(tu.user_whitelist, 'course', 'DESN2000_2020T3_CVEN')
		# print(cven_demos)
		# tu.add_users_to_team('458b02e9-dea0-4f74-8e09-93e95f93b473', cven_demos, role='Owner')

		# add specific users to all channels
		# for d in cven_demos:
		# 	tu.add_user_to_all_channels(d, 'Owner', 'DESN2000_2020T3_CVEN')

		# sync up channels - with many users, this takes a long time (approx 8 commands/minute)
		# tu.update_channels()
