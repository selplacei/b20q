import asyncio
import configparser
import json
import discord

import format
import commands

# Configs
config = configparser.ConfigParser()
config.read('config.cfg')


def update_config():
	with open('config.cfg') as c:
		config.write(c)


# Game status.json
class b20qGame:
	def __init__(self, status=None):
		# Initialize discord.py client
		self.client = Client20q()
		self.channel = None

		# Initialize game status
		self.status = status
		if self.status is None:
			with open('status.json') as status:
				self.status = json.load(status)

		self._confirmation_check = lambda: True

	def __enter__(self):
		return self

	def __exit__(self, type, value, traceback):
		with open('status.json', 'w+') as status:
			json.dump(self.status, status)

	def is_moderator(self, user, guild):
		with open('mods.json') as mods:
			return user.id in json.load(mods).get(guild.id, [])

	async def add_moderator(self, user, guild):
		with open('mods.json') as mods:
			modlist = json.load(mods)
		modlist[guild.id] = modlist.get(guild.id, [])
		modlist[guild.id].append(user.id)
		with open('mods.json', 'w+') as mods:
			json.dump(modlist, mods)

	async def remove_moderator(self, user, guild):
		with open('mods.json') as mods:
			modlist = json.load(mods)
		if guild.id in modlist and user.id in modlist[guild.id]:
			modlist[guild.id].remove(user.id)
			with open('mods.json', 'w+') as mods:
				json.dump(modlist, mods)

	@property
	def prefix(self):
		return config['b20q']['prefix']

	@property
	def defender(self):
		return self.client.get_user(self.status['defender'])

	@defender.setter
	def defender(self, id):
		self.status['defender'] = id

	@property
	def max_questions(self):
		return config.getint('b20q', 'maxQuestions')

	@property
	def max_guesses(self):
		return config.getint('b20q', 'maxGuesses')

	@property
	def allow_hints(self):
		return config.getboolean('b20q', 'allowHints')

	@property
	def allow_vote_end(self):
		return config.getboolean('b20q', 'allowVoteEnd')

	@property
	def warn_mod_only_fail(self):
		return config.getboolean('b20q', 'warnModOnlyFunctions')

	@property
	def answers_left(self) -> int:
		if self.max_questions == -1:
			return -1
		return self.max_questions - len(self.status['answers'])

	async def add_answer(self, correct: bool, answer: str):
		if self.answers_left > 0 or self.answers_left == -1:
			self.status['answers'].append((correct, answer))

	@property
	def guesses_left(self) -> int:
		if self.max_guesses == -1:
			return -1
		return self.max_guesses - len(self.status['guesses'])

	async def add_guess(self, correct: bool, user, guess: str):
		if not correct and (self.guesses_left > 0 or self.answers_left == -1):
			self.status['answers'].append((correct, user.id, guess))
		else:
			await self.end()

	@property
	def winner(self):
		if self.status['guesses'] and self.status['guesses'][-1][0]:
			return self.client.get_user(self.status['guesses'][-1][1])
		else:
			return None

	@property
	def active(self):
		return (self.defender is not None) and ((self.guesses_left != 0) and (self.winner is None))

	async def await_confirmation(self, users, channel, callback, mod_override=False):
		self._confirmation_check = lambda user: user in users or (mod_override and self.is_moderator(user, channel))
		responded = False
		while not responded:
			msg = await self.client.wait_for('message', check=self._confirmation_check)
			if msg.content.startswith(f'{self.prefix} confirm'):
				responded = True
				callback(msg.author)
			elif msg.content.startswith(f'{self.prefix} deny'):
				responded = True

	async def start(self, defender):
		self.status = {
			'defender': defender.id,
			'answers': [],
			'hints': [],
			'guesses': []
		}
		await self.channel.send(f'**A new Questions game has been started!** '
								f'The current defender is {self.defender.mention}.\n'
								f'You have __{"unlimited" if self.max_questions == -1 else self.max_questions}__ '
								f'questions and __{"unlimited" if self.max_guesses == -1 else self.max_guesses}__ '
								f'guesses available.')

	async def end(self):
		await self.channel.send(f'**The Questions game has been ended by the defender,** {self.defender.mention}. '
								f'Type `{self.prefix} show` to see the results so far or '
								f'`{self.prefix} start` to start a new game as the defender.')
		self.status['defender'] = None


# Command implementation
async def execute_command(message):
	_DIRECT_COMMANDS = {
		'start': commands.start,
		'end': commands.end,
		'show': commands.show
	}
	if len(message.content.split()) <= 1:
		return
	command = message.content.split()[1]
	if command in _DIRECT_COMMANDS:
		await _DIRECT_COMMANDS[command](message)
	# add other commands here
	else:
		await game.channel.send(f'Unknown command "{command}".')


class Client20q(discord.Client):
	async def on_message(self, message):
		if message.content.startswith(game.prefix):
			print(f'{message.author.id} {message.author}: {message.content}')
			game.channel = message.channel
			await execute_command(message)


if __name__ == '__main__':
	with b20qGame() as game:
		with open('token') as token:
			_token = token.read().strip()
		commands.game = game
		game.client.run(_token)
