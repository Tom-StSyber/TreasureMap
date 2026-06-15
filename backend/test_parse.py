# save as D:\Home-Lab\TreasureMap\backend\test_parse.py
from ntc_templates.parse import parse_output

raw = """
Cisco IOS Software, Version 15.2(4)M7
Router uptime is 1 week, 3 days
cisco 2901 (revision 1.0) with 491520K bytes of memory.
"""

result = parse_output(platform="cisco_ios", command="show version", data=raw)
print(result)