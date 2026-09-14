"""Start the local desktop installation, ready for UI-controlled Wi-Fi sharing."""
from lan_access import main
import argparse

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', help='Wi-Fi IPv4 address when using multiple adapters or a VPN')
    args = parser.parse_args()
    main('enable', args.host)
    main('open')
