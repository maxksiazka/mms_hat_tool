import argparse
from hat_tool.tui import HatTUI

def main():
    parser = argparse.ArgumentParser(description="Chainbus HAT Management Tool")
    parser.add_argument('action', choices=['register', 'generate', 'remove'], help='Action to perform')
    args = parser.parse_args()

    tui = HatTUI()
    if args.action == 'register':
        tui.register_wizard()
    elif args.action == 'generate':
        tui.generate_wizard()
    elif args.action == 'remove':
        tui.remove_wizard()

if __name__ == "__main__":
    main()
