# b20q

**b20q** is a small Discord bot that allows you to play the 20 questions game.
The numbers of allowed questions and guesses are configurable.

## Installation and Usage

These instructions assume that you are on a Unix-like system and implementations of `git` and `python` are installed.

    git clone https://github.com/selplacei/b20q.git && cd b20q
    chmod +x update.sh
    python3 -m venv venv
    ./venv/bin/pip install -r requirements.txt
    # To launch b20q:
    ./venv/bin/python b20q.py
    # Optionally, create a launch script and use it instead.
    echo './venv/bin/python b20q.py' > launch.sh && chmod +x launch.sh
    # To update b20q:
    ./update.sh

If you already have a bot account and a token ready to go, create a file called "token" and paste the token there.  
Otherwise, follow the instructions at https://discordpy.readthedocs.io/en/latest/discord.html and do the above.


Copyright 2019-2020 Illia Boiko (selplacei) <ilyaviaik@gmail.com>  
The software in this repository is licensed under the Apache 2.0 license, the terms and conditions of which can be
found in the `LICENSE` file.
