# SPDX-License-Identifier: Apache-2.0
import sys
from typing import List, Tuple
from discord import User

import b20q
import commands
import utils

# If a message exceeds Discord's length limit, it will be split into chunks that satisfy the limit.
# If breakpoints exist, b20q will try to split the message at those breakpoints.
# Breakpoints are applied by inserting the result of breakpoint() into the format string at the appropriate place.
# If a string is split at a breakpoint, the preceding message will end in end_l and the latter will start with start_r. 
# If a message has to be split without a breakpoint, b20q.MESSAGE_SPLIT_WARNING will be inserted at the split.
# A breakpoint is a substring starting with BRK1, ending with BRK3, and containing one BRK2.
BRK1, BRK2, BRK3 = '\ue000', '\ue001', '\ue003'


def breakpoint(end_l='', start_r=''):
	return BRK1 + end_l + BRK2 + start_r + BRK3


def _get_name(user):
	try:
		return utils.remove_formatting(commands.game.channel.guild.get_member(user.id).display_name)
	except AttributeError:
		return utils.remove_formatting(user.display_name)


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
	formatted += f'``` {breakpoint()}```diff'
	if not answers:
		formatted += '\nNo answers so far.'
	for i, (correct, answer) in enumerate(answers):
		formatted += f'\n{"+" if correct else "-"} [{i + 1}] {answer}' + breakpoint('```', '```diff')

	# Questions/guesses left
	formatted += f'``` {breakpoint()}```py\n'
	if max_questions == -1:
		formatted += 'You have unlimited questions.\n'
	else:
		formatted += f'Questions answered: {len(answers)}/{max_questions}\n'
	if max_guesses == -1:
		formatted += 'You have unlimited guesses.'
	else:
		formatted += f'You have {(max_guesses - len(guesses))} guesses left.'

	# Hints
	formatted += f'``` {breakpoint()}```bat\n'
	formatted += f'Hints: {"None" if not hints else ""}'
	for i, hint in enumerate(hints):
		formatted += f'\n[{i + 1}] {hint}' + breakpoint('```', '```bat')

	# Guesses
	if guesses or guess_queue:
		formatted += f'``` {breakpoint()}```diff\n'
		formatted += 'Guesses:\n'
		for i, (correct, guesser, guess) in enumerate(guesses):
			formatted += f'{"+" if correct else "-"} [{i + 1}] {_get_name(guesser)}: {guess}{breakpoint("```", "```diff")}\n'
		for guesser, guess in guess_queue:
			formatted += f'? {_get_name(guesser)}: {guess}{breakpoint("```", "```diff")}\n'
		formatted += '```'
	else:
		formatted += f'``` {breakpoint()}```\nNo guesses so far.```'

	return formatted


async def send(defender, answers, max_questions, hints, guesses, guess_queue, max_guesses, max_length=None):
	max_length = max_length or b20q.MAX_MESSAGE_LENGTH
	for fragment in collapse_breakpoints(split_breakpoints(apply(
		defender, answers, max_questions, hints, guesses, guess_queue, max_guesses
	)), max_length):
		await commands.game.send(fragment)


async def send_brief(defender, answers, max_questions, hints, guesses, guess_queue, max_guesses):
	formatted = '```json\n'
	formatted += 'Defender: '
	formatted += f'"{_get_name(defender)} ({defender})"' if defender else 'None (the game is currently not active)'
	formatted += f'\n'
	if max_questions == -1:
		formatted += 'You have unlimited questions.\n'
	else:
		formatted += f'Questions answered: {len(answers)}/{max_questions}\n'
	if max_guesses == -1:
		formatted += 'You have unlimited guesses.\n'
	else:
		formatted += f'You have {(max_guesses - len(guesses))} guesses left.\n'
	formatted += f'Hints: {len(hints)}; Guesses: {len(guesses)}'
	if guess_queue:
		formatted += f'; Pending guesses: {len(guess_queue)}'
	formatted += '```'
	await commands.game.send(formatted)


def split_breakpoints(raw_message):
	# Splits a message produced by apply() into normal parts and breakpoints.
	# A normal part will always be followed by a breakpoint unless it's the last element in the list.
	fragments = []
	partial_message = raw_message
	breakpoint_index = partial_message.find(BRK1)
	while breakpoint_index != -1:
		end_index = partial_message.find(BRK3)
		if end_index == -1:
			raise ValueError(
				f'Problematic format string:\n\n{raw_message}\n\n'
				f'Mismatched BRK1 and BRK3: expected BRK3 after BRK1 at index {breakpoint_index}\n'
				f'\t| {raw_message[breakpoint_index-10:breakpoint_index+10]}\n'
				f'\t|           ^^^'
			)
		fragments.append(partial_message[:breakpoint_index])
		fragments.append(partial_message[breakpoint_index:end_index+1])
		partial_message = partial_message[end_index+1:]
		breakpoint_index = partial_message.find(BRK1)
	fragments.append(partial_message)
	return fragments


def collapse_breakpoints(split_list, max_length):
	# Takes the result of split_breakpoints() and produces a list of fragments to be sent according to max_length.
	fragments = [split_list.pop(0)]
	uncollapsed = split_list
	while len(uncollapsed) > 1:
		# Here, uncollapsed is guaranteed to start with a breakpoint and have a normal part immediately after
		if uncollapsed[0].count(BRK2) != 1:
			raise ValueError(
				f'Problematic format string:\n\n{"".join(split_list)}\n\n'
				f'Expected exactly one BRK2 between BRK1 and BRK3 in the following part:\n'
				f'\t| {fragments[-1][:-10]}'
				f'{uncollapsed[0].replace(BRK1, "{BRK1}").replace(BRK2, "{BRK2}").replace(BRK3, "{BRK3}")}'
			)
		part_l = fragments[-1]
		end_l, start_r = uncollapsed.pop(0).lstrip(BRK1).rstrip(BRK3).split(BRK2)
		part_r = uncollapsed.pop(0)
		if len(part_l) + len(part_r) > max_length:
			fragments[-1] += end_l
			fragments.append(start_r + part_r)
		else:
			fragments[-1] += part_r
	if len(uncollapsed) == 2:
		fragments.append(uncollapsed.pop())
	return fragments
