Inquiry is a bot that makes polls. Nothing more nothing less. Featuring extensive customisation, all you need to do is ask the question. 

[Invite Inquiry](https://discord.com/api/oauth2/authorize?client_id=903968203779215401&permissions=377957124096&scope=bot%20applications.commands)

[Powered by NAFF](https://github.com/NAFTeam/NAFF)

![image](https://user-images.githubusercontent.com/22540825/186192310-653dee1e-972f-4e9e-a24a-ecd946f5d5c4.png)

## So how do you use Inquiry?
Simply type `/poll` and name your poll. From here you can customise the poll to your needs.

Once customised, hit submit, and a modal will appear letting you add your options. 

### All polls have the following optional settings
- `Colour` - What colour should the embed be?
- `Description` - Add a description to your poll
- `Duration` - How long can people vote in this poll?
- `Single_Vote` - Only allow people to have 1 vote in the poll
- `Hide_Results` - Hide the results of the poll until it has closed
- `Open_Poll` - Allow people to add their own options to the poll
- `Thread` - Create a thread for this poll
- `Inline` - Should the options be displayed in line (side-by-side)
- `Image` - Add an image to the poll

## Need a poll fast? 
Use `poll_prefab`. These commands create a poll with pre-set options for you. 

Currently, there are:
- `boolean` - a poll with yes or no options
- `opinion` - a poll with `agree`, `neutral`, `disagree` options
- `week` - a poll with the days of the week
- `blank` - an open poll with no starting options 

## What about custom emoji?
Custom emoji couldnt be simpler; just put an emoji anywhere in the option text, and Inquiry will extract it for the option's emoji

![image](https://user-images.githubusercontent.com/22540825/186945287-9c4f7807-eb1d-4acb-8e83-2772c48ed1f5.png)

![image](https://user-images.githubusercontent.com/22540825/186945315-2b1a99ad-0c70-4374-af77-652684fe8e67.png)


## Made  a mistake?
You can edit polls too, up until you close them. Simply use the `edit_poll` commands

## Want to close the poll?
To automatically close polls, use the `duration` setting, otherwise just react to the poll with 🔴

## How do I self-host this?
While I won't go out of my way to make help you, I can appreciate wanting to host things yourself. 

You'll need three things, redis, docker, and a token. The best part is docker can help with the first one. 

For the token, create a file called `.env`. In it, put your token, like this
```
TOKEN=<token>
```

Fire up your redis server, and run the following command in this projects root dir
```
docker-compose up -d
```
Congrats, Inquiry is now running on your machine.

If you make something cool, please consider creating a PR here.
