"""Run the local application using Kajenn's server."""

import argparse

from kajenn import AsgiServer

from asqueel_dbmanager.app import DbManagerApp, DbManagerWorker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    AsgiServer(applications=[DbManagerApp, DbManagerWorker]).serve(host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
