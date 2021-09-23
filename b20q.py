# SPDX-License-Identifier: Apache-2.0
import sys
import asyncio
import configparser
import json
import os
from collections import OrderedDict
from datetime import datetime
from typing import Awaitable, Optional

import discord

import commands
import utils

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
		self._start_opened = False
		self.confirmation_queue = {}
		self.client = Client20q()

	def __enter__(self):
		return self

	def __exit__(self, type, value, traceback):
		self.save()

	async def ask_for_confirmation(self, user, success_callback: Optional[Awaitable], fail_callback: Optional[Awaitable]):
		# Raises ValueError if the user is already in the confirmation queue.
		if user in self.confirmation_queue:
			raise ValueError(f'{user} is already in the confirmation queue')
		if success_callback is None:
			success_callback = utils.noop()
		if fail_callback is None:
			fail_callback = utils.noop()
		self.confirmation_queue[user] = (success_callback, fail_callback)

	async def send(self, content, *args, **kwargs):
		# Use this instead of channel.send() to implement custom behavior.
		try:
			if len(str(content)) > MAX_MESSAGE_LENGTH:
				fragments = [content[i:i + MAX_MESSAGE_LENGTH] for i in range(0, len(content), MAX_MESSAGE_LENGTH)]
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
		try:
			_status['guess_queue'] = {u.id: g for u, g in _status['guess_queue'].items()}
		except KeyError:
			pass
		return json.dumps(_status, cls=_DiscordUserSerializer)

	async def initialize_status(self):
		try:
			self.load_status()
		except (json.JSONDecodeError, KeyError, ValueError) as e:
			sys.stderr.write(repr(e))
			sys.stderr.write('\nError while loading status from JSON. The status has been reset.\n')
			self.reset_status()
		self.initialized = True

	def load_status(self):
		with open('status.json') as s:
			_status = json.load(s)
		# Convert all user IDs into user objects. If an ID is not found (except in queued guesses), reset the status.
		self.status = self.default_status()
		self.status.update(_status)
		if self.status['defender'] is not None:
			self.status['defender'] = self.client.fetch_user(_status['defender'])
			if self.status['defender'] is None:
				sys.stderr.write('Couldn\'t find the defender user from the saved ID. Resetting game status.\n')
				self.reset_status()
				return
		if self.status['winner'] is not None:
			self.status['winner'] = self.client.fetch_user(_status['winner'])
			if self.status['winner'] is None:
				sys.stderr.write('Couldn\'t find the winner from the saved ID. Resetting game status.\n')
				self.reset_status()
				return
		self.status['guesses'] = []
		for c, i, g in _status['guesses']:
			guesser = self.client.fetch_user(i)
			if guesser is None:
				sys.stderr.write(f'Couldn\'t load guess from user ID {i}. Resetting game status.\n')
				self.reset_status()
				return
			self.status['guesses'].append((c, guesser, g))
		self.status['guess_queue'] = OrderedDict()
		for i, g in _status['guess_queue'].items():
			i = int(i)
			guesser = self.client.fetch_user(i)
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
		self.status = self.default_status()
		if write_json:
			with open('status.json', 'w+') as s:
				json.dump(self.status, s)

	@staticmethod
	def default_status():
		return {
			"winner": None,
			"defender": None,
			"answers": [],
			"hints": [],
			"guesses": [],
			"guess_queue": OrderedDict()
		}

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
		return config['b20q']['prefix'] + ' ' if config['b20q'].getboolean('spaceAfterPrefix') else ''

	@property
	def winner(self):
		return self.status['winner']

	@winner.setter
	def winner(self, value):
		self.status['winner'] = value

	@property
	def start_open_to_all(self):
		return (self.winner is None) or self._start_opened

	@property
	def defender(self):
		return self.status['defender']

	@defender.setter
	def defender(self, value):
		self.status['defender'] = value

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
	def active(self):
		return (self.defender is not None) and ((self.guesses_left != 0) and (self.winner is None))

	async def start(self, defender):
		self.status = {
			'winner': None,
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

	def save(self, filename=None, overwrite=True):
		with open(filename or (
			'status.json' if overwrite else f'status-{datetime.now().strftime("%Y%m%d-%H%M")}.json'
		), 'w') as f:
			f.write(self.status_as_json())


class Client20q(discord.Client):
	async def on_ready(self):
		if 'B20Q_UPDATE_MESSAGE' in os.environ:
			try:
				channel, id = map(int, os.environ['B20Q_UPDATE_MESSAGE'].split(':'))
				message = await self.get_channel(channel).fetch_message(id)
				try:
					await message.remove_reaction('💤', self.user)
				except discord.NotFound:
					pass
				await message.add_reaction('✅')
			except Exception as e:
				sys.stderr.write(f'Error when reading B20Q_UPDATE_MESSAGE: {os.environ["B20Q_UPDATE_MESSAGE"]}\n{e}\n')
		if not game.initialized:
			try:
				await asyncio.wait_for(game.initialize_status(), 20.0)
			except asyncio.TimeoutError:
				sys.stderr.write('Timed out while loading status from JSON. WTF?')
				game.reset_status()

	async def on_message(self, message):
		if message.author != self.user:
			if not game.initialized:
				await message.channel.send('Still initializing. Wait up to 20 seconds and try again.')
			elif message.content.startswith(game.prefix):
				print(f'[{message.guild}] {{{message.author}}} > #{message.channel}: {message.content}')
				game.channel = message.channel
				await commands.execute_command(message)


if __name__ == '__main__':
	with b20qGame() as game:
		with open('token') as token:
			_token = token.read().strip()
		commands.game = game
		asyncio.get_event_loop().run_until_complete(game.client.start(_token))
