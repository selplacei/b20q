# SPDX-License-Identifier: Apache-2.0
import sys
import os
import subprocess
import threading
import time
from collections import OrderedDict

import b20q
import status_format
import utils

game: b20q.b20qGame


async def execute_command(message):
	COMMANDS = {
		'start': start,
		'show': show,
		'status': status, 's': status,
		'help': help_,
		'open': open_,
		'confirm': confirm,
		'deny': deny,

		'edit': edit,
		'delete': delete,
		'hint': hint,
		'answer': answer,
		'yes': answer,
		'no': answer,
		'incorrect': incorrect,
		'correct': correct,
		'end': end,

		'guess': guess,
		'unguess': unguess,

		'mod': mod,
		'unmod': unmod,
		'ismod': is_mod, 'is mod': is_mod, 'am i mod': is_mod,
		'sample': sample,
		'id': id_,
		'save': save,
		'shutdown': shutdown, 'off': shutdown,
		'update': update
	}
	content = message.content.lstrip(game.prefix)
	if len(content) == 0:
		return
	for command, fn in COMMANDS.items():
		if message.content.startswith(f'{game.prefix}{command}'):
			await fn(message)
			break
	else:
		await game.send(f'{message.author.mention} Unknown command "{content.split()[0]}".')


def active_only(fn):
	async def wrapper(message):
		if game.active:
			await fn(message)
		else:
			await message.add_reaction('❌')
	return wrapper


def mod_only(fn):
	async def wrapper(message):
		if game.is_moderator(message.author, message.guild):
			await fn(message)
		else:
			await on_mod_only_fail(message)
	return wrapper


def defender_only(fn):
	async def wrapper(message):
		if message.author == game.defender or game.is_moderator(message.author, message.guild):
			await fn(message)
	return wrapper


def attacker_only(fn):
	async def wrapper(message):
		if message.author != game.defender:
			await fn(message)
	return wrapper


def winner_only(fn):
	async def wrapper(message):
		if message.author == game.winner:
			await fn(message)
	return wrapper


async def on_mod_only_fail(message):
	if game.warn_mod_only_fail:
		await game.send(f'{message.author.mention} This command can only be used by moderators.')


async def confirm(message):
	if message.author in game.confirmation_queue:
		await game.confirmation_queue[message.author][0]
		game.confirmation_queue[message.author][1].cancel()
		del game.confirmation_queue[message.author]
	else:
		await message.add_reaction('❌')


async def deny(message):
	if message.author in game.confirmation_queue:
		await game.confirmation_queue[message.author][1]
		game.confirmation_queue[message.author][0].cancel()
		del game.confirmation_queue[message.author]
	else:
		await message.add_reaction('❌')


@winner_only
async def open_(message):
	game._start_opened = True
	await game.send(
		f'The winner has opened the game to everyone. '
		f'Type `{game.prefix}start` to start; you don\'t need a confirmation.'
	)


async def start(message):
	if game.active:
		await game.send(
			f'A game is already running! The current defender is {game.defender}.\n'
			f'Hint: the current defender can use `{game.prefix}end` to end the game prematurely.\n'
			f'Alternatively, a moderator can use `{game.prefix}force end` to end the current game.'
		)
		return
	if game.start_open_to_all or message.author == game.winner:
		# The game is not active, and the caller isn't interfering with the previous winner's priority.
		await game.start(message.author)
	else:
		try:
			await game.ask_for_confirmation(game.winner, game.start(message.author), None)
			await game.send(
				f'You are attempting to start a new game; however, the previous winner takes priority. '
				f'{game.winner.mention} can give you the OK by sending `{game.prefix}confirm` '
				f'or `{game.prefix}deny` otherwise.'
			)
		except ValueError:
			await game.send(
				f'Someone has already requested the previous winner\'s permission to start the game. '
				f'Wait until {game.winner.mention} sends `{game.prefix}confirm` or `{game.prefix}deny` and try again.'
			)


async def show(message):
	await status_format.send(
		game.defender,
		game.status['answers'],
		game.max_questions,
		game.status['hints'],
		game.status['guesses'],
		game.status['guess_queue'].items(),
		game.max_guesses
	)


async def status(message):
	await status_format.send_brief(
		game.defender,
		game.status['answers'],
		game.max_questions,
		game.status['hints'],
		game.status['guesses'],
		game.status['guess_queue'].items(),
		game.max_guesses
	)


async def help_(message):
	TOPIC_ALIASES = {
		'': '1',
		'b20q': '1',
		'20q': '1',
		'general': '1',
		'defender': '2',
		'attacker': '3',
		'mod': 'modcommands',
		'mod commands': 'modcommands'
	}
	content = message.content.lstrip(game.prefix)
	topic = ' '.join(content.split()[1:]).lower()
	if topic in TOPIC_ALIASES:
		topic = TOPIC_ALIASES[topic]
	if os.path.exists(f'./HelpTopics/{topic}.txt'):
		with open(f'./HelpTopics/{topic}.txt') as helptxt:
			text = helptxt.read().replace('%prefix%', game.prefix)
			if topic != 'modcommands' or game.is_moderator(message.author, message.guild):
				await game.send(f'{message.author.mention}\n{text}')
	elif topic.isdigit():
		await game.send(f'{message.author.mention} Help page not found.')
	else:
		await game.send(f'{message.author.mention} Help topic not found.')


@active_only
@defender_only
async def edit(message):
	args = [game.prefix] + message.content.lstrip(game.prefix).split('\n')[0].split()
	if (len(args) < 5) or (args[2] not in ('answer', 'hint')) or (not args[3].isdigit()):
		await game.send(f'{message.author.mention} Format: `{game.prefix}edit <answer|hint> <index> <result>`')
		return
	index = int(args[3]) - 1
	result = utils.remove_formatting(' '.join(args[4:]))
	if args[2] == 'answer' and (result.startswith('yes ') or result.startswith('no ')):
		try:
			game.status['answers'][index] = (result.startswith('yes '), game.status['answers'][index][1])
			await message.add_reaction('✅')
		except IndexError:
			await message.add_reaction('❌')
		result = ' '.join(result.split()[1:])
		if not result:
			return
	if args[2] == 'answer':
		try:
			game.status['answers'][index] = (game.status['answers'][index][0], result)
			await message.add_reaction('✅')
		except IndexError:
			await message.add_reaction('❌')
	elif args[2] == 'hint':
		try:
			game.status['hints'][index] = result
			await message.add_reaction('✅')
		except IndexError:
			await message.add_reaction('❌')


@active_only
@defender_only
async def delete(message):
	args = [game.prefix] + message.content.lstrip(game.prefix).split()
	if (len(args) < 4) or (args[2] not in ('answer', 'hint')) or (not args[3].isdigit()):
		await game.send(f'{message.author.mention} Format: `{game.prefix}delete <answer|hint> <index>`')
		return
	part = args[2]
	index = int(args[3]) - 1
	try:
		del game.status[part + 's'][index]
		await message.add_reaction('✅')
	except IndexError:
		await message.add_reaction('❌')


@active_only
@defender_only
async def hint(message):
	content = message.content.split('\n')[0].lstrip(game.prefix)
	if len(content.split()) > 1:
		_hint = utils.remove_formatting(' '.join(content.split()[1:]))
		game.status['hints'].append(_hint)
		await game.send(f'**New hint:**\n`{_hint or " "}`')


@active_only
@defender_only
async def answer(message):
	content = message.content.split('\n')[0].lstrip(game.prefix).replace('answer', '', 1).strip()
	if len(content.split()) < 2 or content.split()[0] not in ('yes', 'no'):
		await game.send(f'{message.author.mention} Format: {game.prefix}[answer] <yes|no> <answer>')
	elif game.answers_left == 0:
		await game.send('There are no questions left.')
	else:
		_answer = utils.remove_formatting(' '.join(content.split()[1:]))
		_correct = content.split()[0] == 'yes'
		game.add_answer(_correct, _answer)
		await game.send(f'**New answer:**```diff\n{"+" if _correct else "-"} {_answer or " "}\n```')


async def _confirm_guess(message):
	"""
	Used for correct/incorrect guess confirmations.
	Returns the user whose guess is being confirmed or None if not found.
	"""
	if len(game.status['guess_queue']) == 0:
		await game.send(f'{message.author.mention} There are no active guesses.')
		return None
	elif message.mentions:
		user = message.mentions[0]
		if user not in game.status['guess_queue']:
			await game.send(
				f'That user hasn\'t made any guesses. '
				f'Use `{game.prefix}show` to view the guess queue.'
			)
			return None
		else:
			return user
	elif len(game.status['guess_queue']) == 1:
		return list(game.status['guess_queue'].items())[0][0]
	else:
		await game.send(
			f'{message.author.mention} There are multiple guesses active. '
			f'Please choose a user and try again.'
		)
		return None


@active_only
@defender_only
async def correct(message):
	user = await _confirm_guess(message)
	if user is None:
		return
	game.add_guess(True, user, game.status['guess_queue'][user])
	game.winner = user
	await game.send(
		f'**Game over!** '
		f'The winner is: {user.mention}\nThe correct guess was: __{game.status["guesses"][-1][2]}__'
		f'\n**{len(game.status["answers"])}** questions were asked and '
		f'**{len(game.status["guesses"])}** guesses were made.\n'
		f'The winner may now start a new game with `{game.prefix}start`, request someone else '
		f'to be the defender, or wait until someone asks to defend and confirm it.'
	)
	game.status['guess_queue'] = OrderedDict()
	game.end()


@active_only
@defender_only
async def incorrect(message):
	user = await _confirm_guess(message)
	if user is None:
		return
	game.add_guess(False, user, game.status['guess_queue'][user])
	await game.send(f'**Incorrect guess:** `{game.status["guess_queue"][user]}`')
	del game.status['guess_queue'][user]


@active_only
@defender_only
async def end(message):
	await game.send(
		f'**The 20 Questions game has been ended by the defender,** {message.author.mention}. '
		f'Type `{game.prefix}show` to see the results so far or '
		f'`{game.prefix}start` to start a new game as the defender.'
	)
	game.end()


@active_only
@attacker_only
async def guess(message):
	content = message.content.split('\n')[0].lstrip(game.prefix)
	if len(content.split()) < 2:
		await game.send(f'{message.author.mention} Enter the guess after "{game.prefix}guess" and try again.')
	elif game.guesses_left == 0:
		await game.send('There are no guesses left.')
	elif message.author in game.status['guess_queue']:
		await game.send(
			f'{message.author.mention} Please wait until your guess "'
			f'{game.status["guess_queue"][message.author]}" has been confirmed or denied by the defender.'
		)
	else:
		_guess = utils.remove_formatting(' '.join(content.split()[1:]))
		game.status['guess_queue'][message.author] = _guess
		await game.send(
			f'**New guess:** `{_guess or " "}`\n'
			f'{game.defender.mention} Use _{game.prefix}<correct|incorrect> [user]_ to confirm or '
			f'deny it.\nIf multiple guesses are active, mention the guesser in your command.'
		)


@active_only
@attacker_only
async def unguess(message):
	if message.author in game.status['guess_queue']:
		del game.status['guess_queue'][message.author]
		await message.add_reaction('✅')
	else:
		await message.add_reaction('❌')


@mod_only
async def mod(message):
	if not message.mentions:
		await game.send(f'Format: {game.prefix}mod <user mention>')
	elif game.is_moderator(message.mentions[0], message.guild):
		await game.send('This user is already a moderator on this server.')
	else:
		game.add_moderator(message.mentions[0], message.guild)
		await message.add_reaction('✅')


@mod_only
async def unmod(message):
	if not message.mentions:
		await game.send(f'Format: {game.prefix}mod <user mention>')
	elif not game.is_moderator(message.mentions[0], message.guild):
		await game.send('This user is not a moderator on this server.')
	else:
		game.remove_moderator(message.mentions[0], message.guild)
		await message.add_reaction('✅')


async def is_mod(message):
	user = message.author
	if message.mentions:
		user = message.mentions[0]
	await game.send(
		f'`{user.display_name}` __is'
		f'{"__" if game.is_moderator(user, message.guild) else " not__"} '
		f'a moderator in `{message.guild.name}`.'
	)


@mod_only
async def sample(message):
	await game.send(status_format.apply(
		message.author,
		[(False, 'This guess was incorrect.'), (True, 'This guess was correct.'), (True, 'This one too.')],
		42,
		['Hint 1', 'Hint 2'],
		[(False, message.author, 'Beach'), (True, message.author, 'Bathtub')],
		[],
		-1
	))


@mod_only
async def id_(message):
	if message.mentions:
		await game.send(message.mentions[0].id)
	elif message.content.startswith(f'{game.prefix}id guild'):
		await game.send(message.guild.id)
	else:
		await game.send(message.author.id)


@mod_only
async def save(message):
	content = message.content.lstrip(game.prefix)
	filename = content.split()[1] if len(content.split()) > 1 else 'status.json'
	if filename == 'stdout':
		sys.stdout.write(game.status_as_json())
	elif filename == 'here':
		await game.send(game.status_as_json())
	else:
		with open(filename, 'w') as file:
			file.write(game.status_as_json())
	await message.add_reaction('✅')


@mod_only
async def shutdown(message):
	await message.add_reaction('✅')
	await game.client.close()
	sys.exit(0)


@mod_only
async def update(message):
	with open('status_pre-update.json', 'w') as file:
		file.write(game.status_as_json())
	await message.add_reaction('✅')

	def _update():
		time.sleep(2)
		subprocess.call('./update.sh')
		if os.path.exists('./launch.sh'):
			print('executing launch.sh')
			os.execl('/bin/sh', '/bin/sh', './launch.sh')
		else:
			os.execl('./venv/bin/python', './venv/bin/python', './b20q.py')

	threading.Thread(target=_update).start()
	await game.client.close()
