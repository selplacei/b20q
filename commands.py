import b20q
import format

game: b20q.b20qGame


def mod_only(fn):
	async def wrapper(message):
		if game.is_moderator(message.author):
			await fn(message)
		else:
			await on_mod_only_fail(message)
	return wrapper


async def on_mod_only_fail(message):
	if game.warn_mod_only_fail:
		await message.channel.send(f'{message.author.mention} This command can only be used by moderators.')


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


async def end(message):
	if not game.active:
		await game.channel.send(f'{message.author.mention} No game is currently active.')
	elif message.author == game.defender:
		await game.end()


async def show(message):
	# Test for empty game status
	if (game.status == {
		'defender': None,
		'answers': [],
		'hints': [],
		'guesses': []
	}):
		await message.channel.send(f'{message.author.mention} Nothing to show here.')
	else:
		await message.channel.send(format.apply(
			game.defender,
			game.status['answers'],
			game.max_questions,
			game.status['hints'],
			game.status['guesses'],
			game.max_guesses
		))
