# SPDX-License-Identifier: Apache-2.0
from typing import List, Tuple
from discord import User


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
	formatted = ''

	# Defender
	formatted += '```json\n'
	formatted += 'Defender: '
	formatted += (f'"{_get_name(defender)} ({defender})"' if defender else 'None (the game is currently not active)')

	# Answers
	formatted += '``` ```diff'
	if not answers:
		formatted += '\nNo answers so far.'
	for i, (correct, answer) in enumerate(answers):
		formatted += f'\n{"+" if correct else "-"} [{i + 1}] {answer}'

	# Questions/guesses left
	formatted += '``` ```py\n'
	if max_questions == -1:
		formatted += 'You have unlimited questions.\n'
	else:
		formatted += f'Questions answered: {len(answers)}/{max_questions}\n'
	if max_guesses == -1:
		formatted += 'You have unlimited guesses.'
	else:
		formatted += f'You have {(max_guesses - len(guesses))} guesses left.'

	# Hints
	formatted += '``` ```bat\n'
	formatted += f'Hints: {"None" if not hints else ""}'
	for i, hint in enumerate(hints):
		formatted += f'\n[{i + 1}] {hint}'

	# Guesses
	if guesses or guess_queue:
		formatted += '``` ```diff\n'
		formatted += 'Guesses:\n'
		for i, (correct, guesser, guess) in enumerate(guesses):
			formatted += f'{"+" if correct else "-"} [{i + 1}] {_get_name(guesser)}: {guess}\n'
		for guesser, guess in guess_queue:
			formatted += f'? {_get_name(guesser)}: {guess}\n'
		formatted += '```'
	else:
		formatted += '``` ```\nNo guesses so far.```'

	return formatted
