#!/usr/bin/env nix-shell
#!nix-shell -i python3

import subprocess
import json
import re
import requests
import datetime
import dateutil.parser
from urllib.parse import urlparse
import libversion

from cachecontrol import CacheControl
from cachecontrol.caches import FileCache
from pathlib import Path
from pprint import pprint
from time import sleep
from functools import partial
from collections import defaultdict

import os
import sys

DOT = Path(__file__).resolve().parent
LOAD_META_FROM_PATH = DOT / "loadMetaFromPath.nix"
MASTER = "https://github.com/nixos/nixpkgs/archive/master.tar.gz"
API_TOKEN = os.environ.get('API_TOKEN')

# Keep stats about caching
CACHE_STATS = defaultdict(int)

sess = requests.session()

log = partial(print, file=sys.stderr)
plog = partial(pprint, stream=sys.stderr)

if API_TOKEN is not None:
    sess.auth = tuple(API_TOKEN.split(':'))

else:
    log(
        "No API token set! You can do this by setting the environment variable "
        "API_TOKEN to `<username>:<personal access token>`"
    )

HTTP = CacheControl(sess, cache=FileCache('.webcache'))


def loadVersions(url=MASTER):
    json_output = subprocess.check_output([
        'nix-instantiate', str(LOAD_META_FROM_PATH),
        '--arg', 'url', str(url),
        '--eval', '--json',
        '--read-write-mode',
    ])

    return json.loads(json_output)


def getUserRepoPair(url):
    try:
        parsed = urlparse(url)
    except AttributeError:
        return

    if parsed.netloc != "github.com":
        return

    m = re.match(r'^\/([^/]+)/([^/]+)(?:/|/wiki)?$', parsed.path)
    if m is None:
        log(f'Could not parse github url: {url}')
        return

    user, repo = m.groups()
    return user, repo


def latestRelease(user, repo):
    '''
    See also:

    "GET /repos/:owner/:repo/releases"
    https://developer.github.com/v3/repos/releases/#get-the-latest-release
    '''

    url = f'https://api.github.com/repos/{user}/{repo}/releases'
    resp = HTTP.get(url)
    rateRemaining = resp.headers.get('X-RateLimit-Remaining')

    if rateRemaining is None:
        log('Host did not send X-RateLimit-Remaining header.')
        log('Status code:', resp.status_code)

        return

    rateRemaining = int(rateRemaining)

    if not resp.from_cache and rateRemaining % 100 == 0:
        log(rateRemaining, 'requests remaining this hour!')

    # Save cache stats:
    CACHE_STATS[resp.from_cache] += 1

    if rateRemaining == 0:
        rateReset = int(resp.headers.get('X-RateLimit-Reset'))
        resetDT = datetime.datetime.fromtimestamp(rateReset)
        now = datetime.datetime.now()
        remaining = resetDT-now
        raise requests.HTTPError(
            f"No more rate remaining. More rate will be available at {resetDT} ({remaining} from now.)")

    result = resp.json()
    if 'message' in result:
        return

    if not result:
        # No releases
        return

    verboseMatch = False
    for tag in result:
        release = tag.get('tag_name')
        if tag.get('prerelease'):
            continue
        if skipPrerelease(release):
            log('Skipping non-tagged prerelease', release)
            verboseMatch = True
            continue
        if verboseMatch:
            log('Rescued it with', release, ':)')
        break
    else:
        # No matching releases
        return

    date = dateutil.parser.parse(tag.get('created_at'))

    return release, date


def removePrefix(prefix, string):
    if not string.startswith(prefix):
        return string

    return string[len(prefix):]


def stripRelease(repo, release):
    rawPrefixes = [*'v r version release stable'.split(), repo]
    joiners = [*'- _ . /'.split(), '']
    modifiers = [str.lower, str.upper, str.title, lambda x: x]
    prefixes = [
        modifier(raw) + joiner
        for modifier in modifiers
        for joiner in joiners
        for raw in rawPrefixes
    ]

    for prefix in prefixes:
        release = removePrefix(prefix, release)
    return release


# Filter out pre-releases that weren't marked on GitHub as such
def skipPrerelease(release):
    release = release.lower()
    markers = ["nightly",
               "develop",
               "rc",
               "alpha",
               "beta",
               "snapshot",
               "testing",
               ]

    return any(marker in release for marker in markers)


# Returns either a date object or none.
def parseUnstable(release):
    unstable = "unstable-"

    shouldParse = release.startswith(unstable)

    release_ = removePrefix("unstable-", release)

    try:
        date_obj = datetime.datetime.strptime(release_, "%Y-%m-%d")
    except ValueError:
        if shouldParse:
            log(
                f"Could not parse unstable date {release}! This should probably "
                "be fixed, either in nixpkgs or in this script."
            )
        return

    return date_obj


def getNextVersion(version, homepage):
    userRepo = getUserRepoPair(homepage)

    if userRepo is None:
        return

    nextVersionDate = latestRelease(*userRepo)

    if nextVersionDate is None:
        return

    nextVersion, nextDate = nextVersionDate

    currDate = parseUnstable(version)

    if currDate is not None and nextDate.date() <= currDate.date():
        log(
            f"Discarding unfit version {nextVersion} ({nextDate}), because it "
            f"is older than our current version {version}."
        )
        return

    if skipPrerelease(nextVersion):
        return

    nextVersion = stripRelease(userRepo[1], nextVersion)

    if libversion.version_compare(version, nextVersion) >= 0:
        return

    return nextVersion


def updateLines(meta):
    for name, values in meta.items():
        version = values['version']
        homepage = values['homepage']

        nextVersion = getNextVersion(**values)
        if nextVersion is None:
            continue

        yield name, version, nextVersion


def main():
    try:
        meta = loadVersions()
        for line in updateLines(meta):
            print(" ".join(line))
    finally:
        log("Cached stats:")
        plog(dict(CACHE_STATS))


if __name__ == '__main__':
    main()
