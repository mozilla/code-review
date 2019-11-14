# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import json
import os

from libmozdata.phabricator import PhabricatorAPI


def build_phabricator_api(name: str, url: str, token: str):
    assert url.endswith("/api/"), f"{name} Url {url} does not end with /api/"
    assert token is not None, f"Missing {name} Phabricator token"
    assert len(token) == 32, f"{name} Phabricator token must be 32 characters long"
    return PhabricatorAPI(token, url)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-url",
        help="Phabricator source endpoint",
        default="https://phabricator.services.mozilla.com/api/",
    )
    parser.add_argument(
        "--source-token",
        help="Phabricator source api token",
        default=os.environ.get("PHABRICATOR_SOURCE_TOKEN"),
    )
    parser.add_argument(
        "--dest-url",
        help="Phabricator destination endpoint",
        default="https://phabricator-dev.allizom.org/api/",
    )
    parser.add_argument(
        "--dest-token",
        help="Phabricator destination api token",
        default=os.environ.get("PHABRICATOR_DEST_TOKEN"),
    )
    parser.add_argument(
        "revision_id",
        type=int,
        help="Phabricator source revision ID to copy on the destination server",
    )
    args = parser.parse_args()

    source = build_phabricator_api("Source", args.source_url, args.source_token)
    print(f"Connected on source: {source.url}")
    dest = build_phabricator_api("Destination", args.dest_url, args.dest_token)
    print(f"Connected on destination: {dest.url}")

    # Load the revision to get the top diff PHID
    print(f"Loading revision {args.revision_id}")
    revision = source.load_revision(rev_id=args.revision_id)
    diff_phid = revision["fields"]["diffPHID"]

    # Get the source repo
    repo_phid = revision["fields"]["repositoryPHID"]
    source_repos = source.request(
        "diffusion.repository.search", constraints={"phids": [repo_phid]}
    )
    assert len(source_repos["data"]) == 1, "Missing repository details"
    source_repo = source_repos["data"][0]
    print(f"Source revision is on repository {source_repo['fields']['shortName']}")

    # Get the matching repo on destination
    dest_repos = dest.request(
        "diffusion.repository.search",
        constraints={"shortNames": [source_repo["fields"]["shortName"]]},
    )
    assert len(dest_repos["data"]) == 1, "Missing same repo on destination"
    dest_repo = dest_repos["data"][0]
    print(f"Found matching repository on destination as {dest_repo['phid']}")

    # Load the diffs to get the numerical ID
    print(f"Loading diffs for {diff_phid}")
    source_diffs = source.search_diffs(
        diff_phid=diff_phid, attachments={"commits": True}
    )
    assert len(source_diffs) == 1, "Should only find one diff"
    source_diff = source_diffs[0]

    # Build the new diff properties using source commits
    commits = source_diff["attachments"]["commits"]["commits"]
    assert len(commits) > 0, "Missing commits on source diff"
    new_properties = {
        commit["identifier"]: {
            "author": commit["author"]["name"],
            "authorEmail": commit["author"]["email"],
            "time": 0,
            "message": commit["message"],
            "commit": commit["identifier"],
            "tree": None,
            "parents": commit["parents"],
        }
        for commit in commits
    }

    # Load top raw diff
    raw_diff = source.load_raw_diff(source_diff["id"])
    print(f"Loading raw source diff {source_diff['id']}")

    # Upload it on target repo
    new_diff = dest.request(
        "differential.createrawdiff", diff=raw_diff, repositoryPHID=dest_repo["phid"]
    )
    print(f"Created new diff {new_diff['id']} - {new_diff['phid']}")

    # Attach commit information to setup the author
    dest.request(
        "differential.setdiffproperty",
        diff_id=new_diff["id"],
        name="local:commits",
        data=json.dumps(new_properties),
    )
    print("Set diff properties")

    # Finally create the revision to link all the pieces
    new_rev = dest.request(
        "differential.revision.edit",
        transactions=[
            {"type": "update", "value": new_diff["phid"]},
            {"type": "title", "value": revision["fields"]["title"]},
            {"type": "summary", "value": "Code review bot debug clone."},
        ],
    )
    print(f"New revision created as {dest.url}/D{new_rev['object']['id']}")


if __name__ == "__main__":
    main()
