# SPDX-License-Identifier: Apache-2.0
from typing import List, Tuple
from discord import User

BREAK_POINT = '\ue000\ue000\ue000'


def _get_name(user):
	try:
		return user.display_name
	except AttributeError:
		return user.nick


def apply(
		defender,
		answers: List[Tuple[bool, str]],  # bool: whether it's a yes or a no; str: answer
		max_questions: int,  # -1 for unlimited
		hints: List[str],
		guesses: List[Tuple[bool, User, str]],  # bool: whether it's correct; str: user who guessed; str: guess
		guess_queue: List[Tuple[User, str]],
		max_guesses: int  # -1 for unlimited
	):  # so sad
	# Construct the formatted string here and then return it.
	# Wherever the `BREAK_POINT` substring (defined at the start of this file) appears,
	# the message may be broken up into multiple parts if its length exceeds Discord's limit.
	formatted = ''

	# Defender
	formatted += '```json\n'
	formatted += 'Defender: '
	formatted += (f'"{_get_name(defender)} ({defender})"' if defender else 'None (the game is currently not active)')

	# Answers
	formatted += f'``` {BREAK_POINT}```diff'
	if not answers:
		formatted += '\nNo answers so far.'
	for i, (correct, answer) in enumerate(answers):
		formatted += f'\n{"+" if correct else "-"} [{i + 1}] {answer}'

	# Questions/guesses left
	formatted += f'``` {BREAK_POINT}```py\n'
	if max_questions == -1:
		formatted += 'You have unlimited questions.\n'
	else:
		formatted += f'Questions answered: {len(answers)}/{max_questions}\n'
	if max_guesses == -1:
		formatted += 'You have unlimited guesses.'
	else:
		formatted += f'You have {(max_guesses - len(guesses))} guesses left.'

	# Hints
	formatted += f'``` {BREAK_POINT}```bat\n'
	formatted += f'Hints: {"None" if not hints else ""}'
	for i, hint in enumerate(hints):
		formatted += f'\n[{i + 1}] {hint}'

	# Guesses
	if guesses or guess_queue:
		formatted += f'``` {BREAK_POINT}```diff\n'
		formatted += 'Guesses:\n'
		for i, (correct, guesser, guess) in enumerate(guesses):
			formatted += f'{"+" if correct else "-"} [{i + 1}] {_get_name(guesser)}: {guess}\n'
		for guesser, guess in guess_queue:
			formatted += f'? {_get_name(guesser)}: {guess}\n'
		formatted += '```'
	else:
		formatted += '``` ```\nNo guesses so far.```'

	return formatted


async def send(channel, max_length, defender, answers, max_questions, hints, guesses, guess_queue, max_guesses):
	fragments = apply(
		defender, answers, max_questions, hints, guesses, guess_queue, max_guesses
	).split(BREAK_POINT)
	parts = [fragments.pop(0)]
	while fragments:
		if len(parts[-1] + fragments[0]) <= max_length:
			parts[-1] += fragments.pop(0)
		elif len(fragments[0]) > max_length:
			whole_fragment = fragments.pop(0)
			while len(whole_fragment) > max_length:
				parts.append(whole_fragment[:max_length])
				parts.append('**[Message split due to exceeding maximum length. Formatting may be broken.]**')
				whole_fragment = whole_fragment[max_length:]
			parts.append(whole_fragment)
		else:
			parts.append(fragments.pop(0))
	for part in parts:
		await channel.send(part)
