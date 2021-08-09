# Using PowerShell to add members to a private channel in Teams

## Guide

[https://medium.com/@joaquin.guerrero/adding-bulk-users-to-teams-private-channels-8c9c8e563900][1]

## Setup

Install the MicrosoftTeams module. For now, only preview releases include the `Add-TeamChannelUser` cmdlet, so we’ll have to specify the right version to install.

```pwsh
Install-Module -Name MicrosoftTeams -AllowPrerelease
```

Check whether the `Add-TeamChannelUser` cmdlet is available now

```pwsh
Get-Command -Module MicrosoftTeams
```

## Use

Login first and follow the prompt (browser-based login)

```pwsh
Connect-MicrosoftTeams
```

Find the right Team GroupID where you'll add people by listing all your teams.

```pwsh
Get-Team -user "z1234567@ad.unsw.edu.au"
```

Add someone. This line can of course be integrated into something more elaborate based of a CSV file, etc.

```pwsh
Add-TeamChannelUser -GroupId TEAM_GROUP_ID -DisplayName "CHANNEL_NAME" -user z1234567@ad.unsw.edu.au
```

For example, with a list of names, use a loop like so.

```pwsh
Foreach ($name in $list) {
	Add-TeamChannelUser -GroupId TEAM_GROUP_ID -DisplayName "CHANNEL_NAME" -user $name
}
```

[1]:	https://medium.com/@joaquin.guerrero/adding-bulk-users-to-teams-private-channels-8c9c8e563900