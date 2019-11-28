import os
import b20q
import status_format

game: b20q.b20qGame


async def execute_command(message):
	COMMANDS = {
		'start': start,
		'end': end,
		'show': show,
		'sample': sample,
		'help': help_,
		'id': id_
	}
	if len(message.content[message.content.find(game.prefix):]) <= 1:
		return
	for command, fn in COMMANDS.items():
		if message.content.startswith(f'{game.prefix} {command}'):
			await fn(message)
			break
	else:
		await game.channel.send(f'{message.author.mention} Unknown command "{message.content.split()[1]}".')


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
		game.channel.send(	f'A game is already running! The current defender is {game.defender}.\n'
							f'Hint: the current defender can use `{game.prefix} end` to end the game prematurely.\n'
							f'Alternatively, a moderator can use `{game.prefix} force end` to end the current game.')
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
	# Test for empty game status
	if (game.status == {
		'defender': None,
		'answers': [],
		'hints': [],
		'guesses': []
	}):
		await game.channel.send(f'{message.author.mention} Nothing to show here.')
	else:
		await game.channel.send(status_format.apply(
			game.defender,
			game.status['answers'],
			game.max_questions,
			game.status['hints'],
			game.status['guesses'],
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
	else:
		await game.channel.send(f'{message.author.mention} Help topic not found.')


@defender_only
async def edit(message):
	args = message.content.split()
	if len(args) < 5 or args[2] not in ('answer', 'hint', 'guess') or args[3].isdigit():
		await game.channel.send(f'{message.author.mention} Format: `{game.prefix} edit <answer|hint|guess> <index> <result>`')
		return
	index = int(args[3])
	result = ' '.join(args[4:])
	if args[2] == 'answer' and (result.startswith('yes') or result.startswith('no')):
		try:
			game.status['answer'][index][0] = result.startswith('yes')
			await message.add_reaction('✅')
		except IndexError:
			await game.channel.send(f'{message.author.mention} There\'s no answer at index {index}.')
		result = ' '.join(result.split()[1:])
		if not result:
			return
	if args[2] == 'answer':
		try:
			game.status['answer'][index][1] = result
			await message.add_reaction('✅')
		except IndexError:
			await game.channel.send(f'{message.author.mention} There\'s no answer at index {index}.')
	elif args[2] == 'hint':
		try:
			game.status['hint'][index] = result
			await message.add_reaction('✅')
		except IndexError:
			await game.channel.send(f'{message.author.mention} There\'s no hint at index {index}.')
	if args[2] == 'guess':
		try:
			game.status['answer'][index] = result
			await message.add_reaction('✅')
		except IndexError:
			await game.channel.send(f'{message.author.mention} There\'s no answer at index {index}.')


@defender_only
async def delete(message):
	args = message.content.split()
	if len(args) < 4 or args[2] not in ('answer', 'hint', 'guess') or args[3].isdigit():
		await game.channel.send(f'{message.author.mention} Format: `{game.prefix} delete <answer|hint|guess> <index>`')
		return
	part = args[2]
	index = int(args[3])
	try:
		del game.status[part][index]
		await message.add_reaction('✅')
	except IndexError:
		await message.add_reaction('❌')


@defender_only
async def end(message):
	if not game.active:
		await game.channel.send(f'{message.author.mention} No game is currently active.')
	else:
		await game.end()


@mod_only
async def sample(message):
	await game.channel.send(status_format.apply(
			message.author,
			[(False, 'This guess was incorrect.'), (True, 'This guess was correct.'), (True, 'This one too.')],
			42,
			['Hint 1', 'Hint 2'],
			[(False, message.author, 'Beach'), (True, message.author, 'Bathtub')],
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
