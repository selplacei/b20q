# SPDX-License-Identifier: Apache-2.0
import sys
import os
import subprocess
import threading
import time
from collections import OrderedDict

import b20q
import status_format

game: b20q.b20qGame


async def execute_command(message):
	COMMANDS = {
		'start': start,
		'show': show,
		'help': help_,

		'edit': edit,
		'delete': delete,
		'hint': hint,
		'answer': answer,
		'incorrect': incorrect,
		'correct': correct,
		'end': end,

		'guess': guess,
		'unguess': unguess,

		'sample': sample,
		'id': id_,
		'shutdown': shutdown,
		'off': shutdown,
		'update': update
	}
	if len(message.content.split()) <= 1:
		return
	for command, fn in COMMANDS.items():
		if message.content.startswith(f'{game.prefix} {command}'):
			await fn(message)
			break
	else:
		await game.channel.send(f'{message.author.mention} Unknown command "{message.content.split()[1]}".')


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


async def on_mod_only_fail(message):
	if game.warn_mod_only_fail:
		await game.channel.send(f'{message.author.mention} This command can only be used by moderators.')


async def start(message):
	if game.active:
		await game.channel.send(	f'A game is already running! The current defender is {game.defender}.\n'
							f'Hint: the current defender can use `{game.prefix} end` to end the game prematurely.\n'
							f'Alternatively, a moderator can use `{game.prefix} force end` to end the current game.')
		return
	if message.mentions and message.content.startswith(f'{game.prefix} start <@'):
		if message.author == game.winner:
			# The winner asked someone else to be the defender. Wait for their confirmation.
			user = message.mentions[0]
			await game.await_confirmation([user], message.channel, lambda u: game.start(user))
			return
		else:
			await game.channel.send(f'{message.author.mention} Only the previous game\'s winner can request someone '
									f'else to be the defender.')
			return
	if (not game.winner) or message.author == game.winner:
		# The game is not active, and the caller isn't interfering with the previous winner's priority.
		await game.start(message.author)
		return
	else:
		# Someone else requested to be the defender. Wait for the winner's or a moderator's confirmation.
		await game.await_confirmation([game.winner], message.channel, lambda u: game.start(message.author), True)


async def show(message):
	await game.channel.send(status_format.apply(
			game.defender,
			game.status['answers'],
			game.max_questions,
			game.status['hints'],
			game.status['guesses'],
			game.status['guess_queue'].items(),
			game.max_guesses
	))


async def help_(message):
	TOPIC_ALIASES = {
		'': '0',
		'b20q': '0',
		'20q': '0',
		'general': '0',
		'defender': '1',
		'attacker': '2',
		'mod': 'modcommands',
		'mod commands': 'modcommands'
	}
	topic = ' '.join(message.content.split()[2:]).lower()
	if topic in TOPIC_ALIASES:
		topic = TOPIC_ALIASES[topic]
	if os.path.exists(f'./HelpTopics/{topic}.txt'):
		with open(f'./HelpTopics/{topic}.txt') as helptxt:
			text = helptxt.read().replace('%prefix%', game.prefix)
			if topic != 'modcommands' or game.is_moderator(message.author, message.guild):
				await game.channel.send(f'{message.author.mention}\n{text}')
	elif topic.isdigit():
		await game.channel.send(f'{message.author.mention} Help page not found.')
	else:
		await game.channel.send(f'{message.author.mention} Help topic not found.')


@active_only
@defender_only
async def edit(message):
	args = message.content.split()
	if (len(args) < 5) or (args[2] not in ('answer', 'hint')) or (not args[3].isdigit()):
		await game.channel.send(f'{message.author.mention} Format: `{game.prefix} edit <answer|hint> <index> <result>`')
		return
	index = int(args[3])
	result = ' '.join(args[4:])
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
	args = message.content.split()
	if (len(args) < 4) or (args[2] not in ('answer', 'hint')) or (not args[3].isdigit()):
		await game.channel.send(f'{message.author.mention} Format: `{game.prefix} delete <answer|hint> <index>`')
		return
	part = args[2]
	index = int(args[3])
	try:
		del game.status[part + 's'][index]
		await message.add_reaction('✅')
	except IndexError:
		await message.add_reaction('❌')


@active_only
@defender_only
async def hint(message):
	if len(message.content.split()) > 2:
		_hint = ' '.join(message.content.split()[2:])
		game.status['hints'].append(_hint)
		await game.channel.send(f'**A new hint has been added by {message.author.mention}:**\n`{_hint}`')


@active_only
@defender_only
async def answer(message):
	if len(message.content.split()) < 4 or message.content.split()[2] not in ('yes', 'no'):
		await game.channel.send(f'{message.author.mention} Format: {game.prefix} answer <yes|no> <answer>')
	else:
		_answer = ' '.join(message.content.split()[3:])
		_correct = message.content.split()[2] == 'yes'
		game.add_answer(_correct, _answer)
		await game.channel.send(f'**New answer:**```diff\n{"+" if _correct else "-"} {_answer}\n```')


async def _confirm_guess(message):
	"""
	Used for correct/incorrect guess confirmations.
	Returns the user whose guess is being confirmed or None if not found.
	"""
	if len(game.status['guess_queue']) == 0:
		await game.channel.send(f'{message.author.mention} There are no active guesses.')
		return None
	elif message.mentions:
		user = message.mentions[0]
		if user not in game.status['guess_queue']:
			await game.channel.send(
				f'That user hasn\'t made any guesses. '
				f'Use `{game.prefix} show` to view the guess queue.'
			)
			return None
		else:
			return user
	elif len(game.status['guess_queue']) == 1:
		return list(game.status['guess_queue'].items())[0][0]
	else:
		await game.channel.send(
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
	await game.channel.send(
		f'**Game over!** '
		f'The winner is: {user.mention}\n__The correct guess was:__ **{game.status["guesses"][-1][2]}**'
		f'\n**{len(game.status["answers"])}** questions were asked and '
		f'**{len(game.status["guesses"])}** guesses were made.\n'
		f'The winner may now start a new game with `{game.prefix} start`, request someone else '
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
	await game.channel.send(f'**Incorrect guess:** `{game.status["guess_queue"][user]}`')
	del game.status['guess_queue'][user]


@active_only
@defender_only
async def end(message):
	await game.channel.send(
		f'**The 20 Questions game has been ended by the defender,** {message.author.mention}. '
		f'Type `{game.prefix} show` to see the results so far or '
		f'`{game.prefix} start` to start a new game as the defender.')
	game.end()


@active_only
@attacker_only
async def guess(message):
	if len(message.content.split()) < 3:
		await game.channel.send(f'{message.author.mention} Enter the guess after "{game.prefix} guess" and try again.')
	elif message.author in game.status['guess_queue']:
		await game.channel.send(
			f'{message.author.mention} Please wait until your guess "'
			f'{game.status["guess_queue"][message.author]}" has been confirmed or denied by the defender.'
		)
	else:
		_guess = ' '.join(message.content.split()[2:])
		game.status['guess_queue'][message.author] = _guess
		await game.channel.send(
			f'**New guess:** `{_guess}`\n'
			f'{game.defender.mention} Use _{game.prefix} <correct|incorrect> [user]_ to confirm or '
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
async def sample(message):
	await game.channel.send(status_format.apply(
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
		await game.channel.send(message.mentions[0].id)
	elif message.content.startswith(f'{game.prefix} id guild'):
		await game.channel.send(message.guild.id)
	else:
		await game.channel.send(message.author.id)


@mod_only
async def shutdown(message):
	await message.add_reaction('✅')
	await game.client.close()
	sys.exit(0)


@mod_only
async def update(message):
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
