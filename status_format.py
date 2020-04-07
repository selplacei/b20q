# SPDX-License-Identifier: Apache-2.0
import sys
from typing import List, Tuple
from discord import User

import b20q
import commands

# If a message exceeds Discord's length limit, it will be split into chunks that satisfy the limit.
# If breakpoints exist, b20q will try to split the message at those breakpoints.
# A breakpoint is a substring consisting of three parts:
# - the start, equal to BRK1;
# - the middle, made of a substring followed by BRK2. If a split happens at the breakpoint, the preceding message
#   will end in that substring.
# - the end, made of a substring followed by BRK3. If a split happens at the breakpoint, the latter message will
#   start with that substring.
# The start/end substrings may not contain any of BRK1, BRK2, or BRK3.
# Every BRK1 should have a matching BRK2 and BRK3.
# If a message has to be split without a breakpoint, b20q.MESSAGE_SPLIT_WARNING will be inserted at the split.
BRK1 = '\ue000'
BRK2 = '\ue001'
BRK3 = '\ue002'
BRK_EMPTY = BRK1 + BRK2 + BRK3


def _get_name(user):
	try:
		return commands.game.channel.guild.get_member(user.id).display_name
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
	formatted += f'``` {BRK_EMPTY}```diff'
	if not answers:
		formatted += '\nNo answers so far.'
	for i, (correct, answer) in enumerate(answers):
		formatted += f'\n{"+" if correct else "-"} [{i + 1}] {answer}{BRK1}```{BRK2}```diff{BRK3}'

	# Questions/guesses left
	formatted += f'``` {BRK_EMPTY}```py\n'
	if max_questions == -1:
		formatted += 'You have unlimited questions.\n'
	else:
		formatted += f'Questions answered: {len(answers)}/{max_questions}\n'
	if max_guesses == -1:
		formatted += 'You have unlimited guesses.'
	else:
		formatted += f'You have {(max_guesses - len(guesses))} guesses left.'

	# Hints
	formatted += f'``` {BRK_EMPTY}```bat\n'
	formatted += f'Hints: {"None" if not hints else ""}'
	for i, hint in enumerate(hints):
		formatted += f'\n[{i + 1}] {hint}{BRK1}```{BRK2}```bat{BRK3}'

	# Guesses
	if guesses or guess_queue:
		formatted += f'``` {BRK_EMPTY}```diff\n'
		formatted += 'Guesses:\n'
		for i, (correct, guesser, guess) in enumerate(guesses):
			formatted += f'{"+" if correct else "-"} [{i + 1}] {_get_name(guesser)}: {guess}{BRK1}```{BRK2}```diff{BRK3}\n'
		for guesser, guess in guess_queue:
			formatted += f'? {_get_name(guesser)}: {guess}{BRK1}```{BRK2}```diff{BRK3}\n'
		formatted += '```'
	else:
		formatted += f'``` {BRK_EMPTY}```\nNo guesses so far.```'

	return formatted


async def send(defender, answers, max_questions, hints, guesses, guess_queue, max_guesses, max_length=None):
	max_length = max_length or b20q.MAX_MESSAGE_LENGTH
	for fragment in collapse_breakpoints(split_breakpoints(apply(
		defender, answers, max_questions, hints, guesses, guess_queue, max_guesses
	)), max_length):
		await commands.game.send(fragment)


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
	# This also splits normal parts if they exceed max_length, even if they don't contain a breakpoint.
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
