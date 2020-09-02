from teams_updater import ClassItem, User, TeamsUpdater

my_path = 'engg1000-engineering-design---2020-t3.csv'

# list of ClassItem instances
my_classes_list = [
	ClassItem(1111, 'Demonstrators', '9ddedadf-879a-43bb-a463-93f85cbe2071', 'ENGG1000_2020T3')
]

# list of User instances
my_user_whitelist = []

if __name__ == '__main__':
	with TeamsUpdater(my_path, my_classes_list, my_user_whitelist) as tu:
		# tu.connect()

		tu.import_user_list()
		# tu.get_channels_user_list()

		# create channels - use step only when necessary
		# tu.create_channels(owners=ows)

		# add people to a team
		# demos = tu.find_users(tu.user_whitelist, 'course', 'ENGG1000_2020T3')
		# print(demos)
		# tu.add_users_to_team('9ddedadf-879a-43bb-a463-93f85cbe2071', demos, role='Owner')

		# add specific users to all channels
		# for d in cven_demos:
		# 	tu.add_user_to_all_channels(d, 'Owner', 'ENGG1000_2020T3')

		# sync up channels - with many users, this takes a long time (approx 8 commands/minute)
		# tu.update_channels()
