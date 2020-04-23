import re


def remove_formatting(text):
	re_strip = (
		(r'(\*{1,3})(.+?)\1', '*'),
		(r'(\_{1,3})(.+?)\1', '_'),
		(r'```([^`]+?)```', '```'),
		(r'`([^`\r\n]+?)`', '`')
	)
	re_strip_one = (
		(r'(\~\~)(.+?)\1', '~~'),
		(r'(\|\|)(.+?)\1', '||')
	)
	re_special_code_block = r'```\w+$'
	
	text = re.sub(re_special_code_block, '', text)
	for regex, char in re_strip:
		for match in re.finditer(regex, text):
			text = text.replace(match.group(), match.group().strip(char))
	for regex, substr in re_strip_one:
		for match in re.finditer(regex, text):
			text = text.replace(match.group(), match.group()[len(substr):-len(substr)])
	return text
