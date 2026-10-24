#!/usr/bin/env bash
# Run one command in the production web component; prints its output with
# secrets masked. See tools/prod_run.py.
#
#   tools/prod_run.sh "/opt/venv/bin/python manage.py showmigrations home | tail -3"
#
# The doctl access token is read from doctl's own config file into this
# process's environment and handed to the container by name (-e NAME), so
# it never appears on a command line, in output or in a log.
set -euo pipefail

if [ $# -ne 1 ]; then
  echo 'usage: tools/prod_run.sh "<shell command>"' >&2
  exit 64
fi

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(dirname "$here")"
repo_mount="$(cygpath -m "$repo" 2>/dev/null || echo "$repo")"

cfg="${DOCTL_CONFIG:-${APPDATA:-}/doctl/config.yaml}"
[ -f "$cfg" ] || cfg="$HOME/.config/doctl/config.yaml"
if [ ! -f "$cfg" ]; then
  echo "doctl isn't configured. Run: doctl auth init" >&2
  exit 1
fi
DIGITALOCEAN_ACCESS_TOKEN="$(sed -n 's/^access-token:[[:space:]]*//p' "$cfg" | head -1 | tr -d "\"'")"
if [ -z "$DIGITALOCEAN_ACCESS_TOKEN" ]; then
  echo "No access-token in doctl's config. Run: doctl auth init" >&2
  exit 1
fi
export DIGITALOCEAN_ACCESS_TOKEN

# A local tool image: the dev image (which trusts this machine's TLS-inspection
# root) plus the Linux doctl binary, pinned to the same version as on Windows.
DOCTL_VERSION="1.167.0"
image="sog-prodrun:doctl-$DOCTL_VERSION"
if ! docker image inspect "$image" >/dev/null 2>&1; then
  tarball="https://github.com/digitalocean/doctl/releases/download/v$DOCTL_VERSION/doctl-$DOCTL_VERSION-linux-amd64.tar.gz"
  {
    echo 'FROM sitesofgrace-web-dev'
    echo 'USER root'
    echo "RUN python -c \"import urllib.request,tarfile,io; d=urllib.request.urlopen('$tarball').read(); tarfile.open(fileobj=io.BytesIO(d)).extract('doctl','/usr/local/bin')\" && doctl version"
    echo 'USER wagtail'
  } | docker build -q -t "$image" - >/dev/null
fi

MSYS_NO_PATHCONV=1 docker run --rm \
  -e DIGITALOCEAN_ACCESS_TOKEN -e SOG_TIMEOUT \
  -v "$repo_mount/tools/prod_run.py:/opt/prod_run.py:ro" \
  "$image" python /opt/prod_run.py "$1"
