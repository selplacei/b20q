# SPDX-License-Identifier: Apache-2.0
import sys
import asyncio
import configparser
import json
from collections import OrderedDict

import discord

import commands

MAX_MESSAGE_LENGTH = 2000
MESSAGE_SPLIT_WARNING = '**[Message split due to exceeding the length limit. Formatting may be broken.]**'

config = configparser.ConfigParser()
config.read('config.cfg')


def update_config_file():
	with open('config.cfg') as c:
		config.write(c)


class _DiscordUserSerializer(json.JSONEncoder):
	def default(self, o):
		if isinstance(o, discord.User) or isinstance(o, discord.Member):
			return o.id
		return super().default(o)


# Game state
class b20qGame:
	def __init__(self):
		self.status = {}
		self.channel = None
		self.initialized = False
		self._confirmation_check = None
		self.client = Client20q()

	def __enter__(self):
		return self

	def __exit__(self, type, value, traceback):
		# Save the game status to the JSON file
		with open('status.json', 'w') as status:
			status.write(self.status_as_json())

	async def send(self, content, *args, **kwargs):
		# Use this instead of channel.send() to implement custom behavior.
		try:
			if len(content) > MAX_MESSAGE_LENGTH:
				fragments = [content[i:i+MAX_MESSAGE_LENGTH] for i in range(0, len(content), MAX_MESSAGE_LENGTH)]
				parts = [None, MESSAGE_SPLIT_WARNING] * len(fragments)
				parts[0::2] = fragments
				parts.pop()
				for part in parts:
					await self.channel.send(part, *args, **kwargs)
			else:
				await self.channel.send(content, *args, **kwargs)
		except Exception as e:
			await self.channel.send(
				f'An exception occurred when sending this message:\n'
				f'{str(e)}'
			)
			raise

	def status_as_json(self):
		_status = self.status.copy()
		_status['guess_queue'] = {u.id: g for u, g in _status['guess_queue'].items()}
		return json.dumps(_status, cls=_DiscordUserSerializer)

	async def initialize_status(self):
		try:
			self.load_status()
		except (json.JSONDecodeError, KeyError, ValueError) as e:
			sys.stderr.write(str(e))
			sys.stderr.write('\nError while loading status from JSON. The status has been reset.\n')
			self.reset_status()
		self.initialized = True

	def load_status(self):
		with open('status.json') as s:
			_status = json.load(s)
		# Convert all user IDs into user objects. If an ID is not found (except in queued guesses), reset the status.
		self.status = _status.copy()
		if self.status['defender'] is not None:
			self.status['defender'] = self.client.get_user(_status['defender'])
			if self.status['defender'] is None:
				sys.stderr.write('Couldn\'t find the defender user from the saved ID. Resetting game status.\n')
				self.reset_status()
				return

		self.status['guesses'] = []
		for c, i, g in _status['guesses']:
			guesser = self.client.get_user(i)
			if guesser is None:
				sys.stderr.write(f'Couldn\'t load guess from user ID {i}. Resetting game status.\n')
				self.reset_status()
				return
			self.status['guesses'].append((c, guesser, g))

		self.status['guess_queue'] = OrderedDict()
		for i, g in _status['guess_queue'].items():
			i = int(i)
			guesser = self.client.get_user(i)
			if guesser is None:
				sys.stderr.write(f'Couldn\'t load queued guess from user ID {i}. Removing the guess.\n')
			else:
				self.status['guess_queue'][guesser] = g
		sys.stderr.write('Finished loading game status from JSON.\n')

	def reset_status(self, write_json=True):
		with open('status.json') as s:
			print(
				f'Resetting status. '
				f'Status stored in memory:\n'
				f'{self.status}\n'
				f'Previous contents of status.json:\n'
				f'{s.read()}\n'
				f'Writing to JSON file: {write_json}'
			)
		self.status = {
			"defender": None,
			"answers": [],
			"hints": [],
			"guesses": [],
			"guess_queue": OrderedDict()
		}
		if write_json:
			with open('status.json', 'w+') as s:
				json.dump(self.status, s)

	def is_moderator(self, user, guild):
		with open('mods.json') as mods:
			return user.id in json.load(mods).get(str(guild.id), [])

	def add_moderator(self, user, guild):
		with open('mods.json') as mods:
			modlist = json.load(mods)
		modlist[guild.id] = modlist.get(str(guild.id), [])
		modlist[guild.id].append(user.id)
		with open('mods.json', 'w+') as mods:
			json.dump(modlist, mods)

	def remove_moderator(self, user, guild):
		with open('mods.json') as mods:
			modlist = json.load(mods)
		if str(guild.id) in modlist and user.id in modlist[str(guild.id)]:
			modlist[str(guild.id)].remove(user.id)
			with open('mods.json', 'w+') as mods:
				json.dump(modlist, mods)

	@property
	def prefix(self):
		return config['b20q']['prefix']

	@property
	def defender(self):
		return self.status['defender']

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
	def warn_mod_only_fail(self):
		return config.getboolean('b20q', 'warnModOnlyFunctions')

	@property
	def answers_left(self) -> int:
		if self.max_questions == -1:
			return -1
		return self.max_questions - len(self.status['answers'])

	def add_answer(self, correct: bool, answer: str):
		self.status['answers'].append((correct, answer))

	@property
	def guesses_left(self) -> int:
		if self.max_guesses == -1:
			return -1
		return self.max_guesses - len(self.status['guesses'])

	def add_guess(self, correct: bool, user, guess: str):
		self.status['guesses'].append((correct, user, guess))

	@property
	def winner(self):
		if self.status['guesses']:
			return self.client.get_user(next((g[1] for g in self.status['guesses'] if g[0]), None))
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
			if msg.content.startswith(f'{self.prefix}confirm'):
				responded = True
				callback(msg.author)
			elif msg.content.startswith(f'{self.prefix}deny'):
				responded = True

	async def start(self, defender):
		self.status = {
			'defender': defender,
			'answers': [],
			'hints': [],
			'guesses': [],
			'guess_queue': {}
		}
		await self.channel.send(
			f'**A new Questions game has been started!** '
			f'The current defender is {self.defender.mention}.\n'
			f'You have __{"unlimited" if self.max_questions == -1 else self.max_questions}__ '
			f'questions and __{"unlimited" if self.max_guesses == -1 else self.max_guesses}__ '
			f'guesses available.'
		)

	def end(self):
		self.status['defender'] = None


class Client20q(discord.Client):
	async def on_message(self, message):
		if not game.initialized:
			try:
				await asyncio.wait_for(game.initialize_status(), 20.0)
			except asyncio.TimeoutError:
				sys.stderr.write('Timed out while loading status from JSON.')
				game.reset_status(write_json=False)
		if message.content.startswith(game.prefix):
			print(f'[{message.guild}] {{{message.author}}} > #{message.channel}: {message.content}')
			game.channel = message.channel
			await commands.execute_command(message)


if __name__ == '__main__':
	with b20qGame() as game:
		with open('token') as token:
			_token = token.read().strip()
		commands.game = game
		game.client.run(_token)
