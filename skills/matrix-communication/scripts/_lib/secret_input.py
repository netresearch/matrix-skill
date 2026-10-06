# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""Read a secret (password, recovery key, passphrase) without putting it on argv.

Stdlib only.

A command-line argument is visible to every local user through the process
list (``ps``, ``/proc/<pid>/cmdline``) for as long as the command runs, and it
lands in shell history. Secrets are therefore read from an environment
variable or an interactive prompt. A value on the command line is accepted
only with ``--allow-secret-argument``, which exists for scripts that cannot
use either.
"""

import getpass
import os

ALLOW_FLAG = "--allow-secret-argument"


class SecretInputError(Exception):
    """The secret was given in a way this command refuses, or not at all."""


def read_secret(
    argv_value,
    env_name: str,
    prompt: str,
    allow_argument: bool = False,
    interactive=None,
    ask=getpass.getpass,
):
    """Return the secret, or None when none was requested.

    ``argv_value`` is what the option received: None when it was not given,
    an empty string when it was given without a value (prompt for it), or the
    value itself (refused unless ``allow_argument``).
    """
    if argv_value:
        if not allow_argument:
            raise SecretInputError(
                f"Refusing a secret on the command line: other local users can "
                f"read it in the process list. Set {env_name}, give the option "
                f"without a value to be prompted, or pass {ALLOW_FLAG}."
            )
        return argv_value
    from_env = os.environ.get(env_name)
    if from_env:
        return from_env
    if argv_value is None:
        return None
    if interactive is None:
        interactive = os.isatty(0)
    if not interactive:
        raise SecretInputError(
            f"No terminal to prompt on. Set {env_name} for non-interactive use."
        )
    value = ask(prompt)
    if not value:
        raise SecretInputError("The secret cannot be empty.")
    return value
