import os
import sys
import traceback
import argparse
from argparse import RawTextHelpFormatter
from cmd.web import phase_open_web
from cmd.keyring import show_keyring_info
from utils.ascii import phaseASCii
from cmd.phase import (
    phase_run_inject,
    phase_list_secrets,
    phase_secrets_get, 
    phase_cli_logout, 
    phase_secrets_env_export, 
    phase_secrets_env_import, 
    phase_secrets_delete, 
    phase_secrets_create,
    phase_secrets_update, 
    phase_init, 
    phase_auth
)
from utils.const import __version__

def print_phase_cli_version():
    print(f"Version: {__version__}")

def print_phase_cli_version_only():
    print(f"{__version__}")

PHASE_DEBUG = os.environ.get('PHASE_DEBUG', 'False').lower() == 'true'

class CustomHelpFormatter(argparse.HelpFormatter):
    def add_usage(self, usage, actions, groups, prefix=None):
        if prefix is None:
            prefix = 'Commands: '
        return super(CustomHelpFormatter, self)

class HelpfulParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs['formatter_class'] = CustomHelpFormatter
        super().__init__(*args, **kwargs)
        
    def error(self, message):
        print(phaseASCii)
        self.print_help()
        sys.exit(2)

    def add_subparsers(self, **kwargs):
        kwargs['title'] = 'Commands'
        return super(HelpfulParser, self).add_subparsers(**kwargs)

if __name__ == '__main__':

    try:
        parser = HelpfulParser(prog='phase-cli', formatter_class=RawTextHelpFormatter)
        parser.add_argument('--version', '-v', action='version', version=__version__)
        
        # Create subparsers with title 'Available Commands:'
        subparsers = parser.add_subparsers(dest='command', required=True)

        # Auth command
        auth_parser = subparsers.add_parser('auth', help='💻 Authenticate with Phase')

        # Init command
        init_parser = subparsers.add_parser('init', help='🔗 Link your project to your Phase app')

        # Run command
        run_parser = subparsers.add_parser('run', help='🚀 Run and inject secrets to your app')
        run_parser.add_argument('command_to_run', nargs=argparse.REMAINDER, help='Command to be run. Ex. phase run yarn dev')

        # Secrets command
        secrets_parser = subparsers.add_parser('secrets', help='🗝️` Manage your secrets')
        secrets_subparsers = secrets_parser.add_subparsers(dest='secrets_command', required=True)

        # Secrets list command
        secrets_list_parser = secrets_subparsers.add_parser('list', help='📇 List all the secrets')
        secrets_list_parser.add_argument('--show', action='store_true', help='Show uncensored secrets')

        # Secrets get command
        secrets_get_parser = secrets_subparsers.add_parser('get', help='🔍 Get a specific secret by key')
        secrets_get_parser.add_argument('key', type=str, help='The key associated with the secret to fetch')

        # Secrets create command
        secrets_create_parser = secrets_subparsers.add_parser('create', help='💳 Create a new secret')
        secrets_create_parser.add_argument('key', type=str, nargs='?', help='The key for the secret to be created')

        # Secrets update command
        secrets_update_parser = secrets_subparsers.add_parser('update', help='📝 Update an existing secret')
        secrets_update_parser.add_argument('key', type=str, help='The key associated with the secret to update')

        # Secrets delete command
        secrets_delete_parser = secrets_subparsers.add_parser('delete', help='🗑️` Delete a secret')
        secrets_delete_parser.add_argument('keys', nargs='*', help='Keys to be deleted')

        # Secrets import command
        secrets_import_parser = secrets_subparsers.add_parser('import', help='📩 Import secrets from a .env file')
        secrets_import_parser.add_argument('env_file', type=str, help='The .env file to import')

        # Secrets export command
        secrets_export_parser = secrets_subparsers.add_parser('export', help='🥡 Export secrets to a .env file')

        # Logout command
        logout_parser = subparsers.add_parser('logout', help='🪪 Logout from phase-cli')
        logout_parser.add_argument('--purge', action='store_true', help='Purge all local data')

        # Web command
        web_parser = subparsers.add_parser('console', help='🖥️` Open the Phase Console in your browser')

        # Keyring command
        keyring_parser = subparsers.add_parser('keyring', help='🔐 Display information about the Phase keyring')

        args = parser.parse_args()

        if args.command == 'auth':
            phase_auth()
            sys.exit(0)
        if args.command == 'init':
            phase_init()
        elif args.command == 'run':
            command = ' '.join(args.command_to_run)
            phase_run_inject(command)
        elif args.command == 'logout':
            phase_cli_logout(args.purge)
        elif args.command == 'console':
            phase_open_web()
        elif args.command == 'keyring':
            show_keyring_info()
        elif args.command == 'secrets':
            if args.secrets_command == 'list':
                phase_list_secrets(args.show)
            elif args.secrets_command == 'get':
                phase_secrets_get(args.key)  
            elif args.secrets_command == 'create':
                phase_secrets_create(args.key)
            elif args.secrets_command == 'delete':
                phase_secrets_delete(args.keys)  
            elif args.secrets_command == 'import':
                phase_secrets_env_import(args.env_file)
            elif args.secrets_command == 'export':
                phase_secrets_env_export()
            elif args.secrets_command == 'update':
                phase_secrets_update(args.key)
            else:
                print("Unknown secrets sub-command: " + args.secrets_command)
                parser.print_help()
                sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopping Phase.")
        sys.exit(0)
        
    except Exception as e:
        if os.getenv("PHASE_DEBUG") == "True":
            # When PHASE_DEBUG is set to True, print the full traceback
            traceback.print_exc()
        else:
            # When PHASE_DEBUG is set to False, print only the error message
            print(str(e))
        sys.exit(1)