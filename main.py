#!/usr/bin/env nix-shell
#!nix-shell -p "python3.withPackages (p: with p; [requests])" -i python3

import subprocess
import json
import re
import requests
from urllib.parse import urlparse

from pathlib import Path
from pprint import pprint
from time import sleep
from functools import partial

import os
import sys

DOT = Path(__file__).resolve().parent
LOAD_META_FROM_PATH = DOT / "loadMetaFromPath.nix"
MASTER = "https://github.com/nixos/nixpkgs/archive/master.tar.gz"
API_TOKEN = os.environ.get('API_TOKEN')

HTTP = requests.session()

log = partial(print, file=sys.stderr)

if API_TOKEN is not None:
    HTTP.auth = tuple(API_TOKEN.split(':'))


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

    m = re.match(r'^\/([\w\-]+)/([\w\-]+)/?$', parsed.path)
    if m is None:
        return

    user, repo = m.groups()
    return user, repo


def latestRelease(user, repo):
    '''
    See also:

    "GET /repos/:owner/:repo/releases/latest"
    https://developer.github.com/v3/repos/releases/#get-the-latest-release
    '''

    url = f'https://api.github.com/repos/{user}/{repo}/releases/latest'
    resp = HTTP.get(url)

    rateRemaining = int(resp.headers['X-RateLimit-Remaining'])
    if rateRemaining % 100 == 0:
        log(rateRemaining, 'requests remaining this hour!')

    if rateRemaining == 0:
        raise requests.HTTPError("No more rate remaining")

    result = resp.json()
    if 'message' in result:
        return

    # pprint(result)
    return result.get('tag_name')


def removePrefix(prefix, string):
    if not string.startswith(prefix):
        return string

    return string[len(prefix):]


def stripRelease(repo, release):
    prefixes = ['V',
                'v',
                'V-',
                'v-',
                'V_',
                'v_',
                'V.',
                'v.',
                "version",
                'release',
                "release_",
                "RELEASE.",
                "stable-",
                repo.lower() + '-',
                repo.lower() + '_',
                repo.lower() + '.',
                repo.upper() + '-',
                repo.upper() + '_',
                repo.upper() + '.',
               ]
    for prefix in prefixes:
        release = removePrefix(prefix, release)
    return release

# Filter out pre-releases that weren't marked on GitHub as such
def skipPrerelease(release):
    lower = release.lower()
    markers = ["nightly",
               "develop",
               "rc",
               "alpha",
               "beta",
               "snapshot",
               "testing",
              ]
    for marker in markers:
        if marker in release:
            return True
    return False

def getNextVersion(version, homepage):
    userRepo = getUserRepoPair(homepage)

    if userRepo is None:
        return

    nextVersion = latestRelease(*userRepo)

    if nextVersion is None:
        return

    # If this version matches the previous version, discard it.
    # We can't do `version in nextVersion`, because it would discard
    # 0.1 => 0.1.1
    if nextVersion.endswith(version):
        return

    if skipPrerelease(nextVersion):
        return

    stripped = stripRelease(userRepo[1], nextVersion)

    return stripped


def updateLines(meta):
    for name, values in meta.items():
        version = values['version']
        homepage = values['homepage']

        nextVersion = getNextVersion(**values)
        if nextVersion is None:
            continue

        yield name, version, nextVersion


def main():
    meta = loadVersions()
    for line in updateLines(meta):
        print(", ".join(line))


if __name__ == '__main__':
    main(
)
