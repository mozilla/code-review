import os
import socket
import sys
import time
from urllib.parse import urlparse


def connect(host, port):
    client = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM)
    try:
        client.connect((host, port))
        client.close()
    except Exception as e:
        print(f"Failed to connect: {e!r}", file=sys.stderr)
        return False

    return True


def main():
    # Get Database URL
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise Exception("Missing DATABASE_URL environment variable")

    # Get host from that database url
    parts = urlparse(db_url)
    host = parts.hostname
    port = parts.port or 5432
    print(f"Checking Postgres host is up at {host} (port {port})", file=sys.stderr)

    # Try to connect to the DB opening a TCP socket
    max_tries = 20
    for i in range(max_tries):
        print(f"Try {i+1}/{max_tries}", file=sys.stderr)

        if connect(host, port):
            print("Connection successful", file=sys.stderr)
            return

        # Wait a bit until next try
        time.sleep(2)

    # All tries failed, so we fail the script too
    raise Exception("All tries failed, DB is not available")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e!r}", file=sys.stderr)
        sys.exit(1)
