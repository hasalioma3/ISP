#!/bin/bash
# Runs ON the Pi: pull the latest code from GitHub, then do the usual
# update (DB backup, cached rebuild, recreate changed containers, migrate)
# via update_on_pi.sh. The GitHub-based alternative to deploy_update.sh,
# which pushes from the Mac with rsync instead.
#
#   ./update_from_github.sh            # deploys origin/main
#   ./update_from_github.sh Phase-2    # deploys another branch
#
# One-time setup (a read-only deploy key and turning ~/ISP into a clone) is
# in DEPLOY.md under "Updating from GitHub".
#
# Server-only files survive: .env.prod, .env.test, companies/*.env and the
# Docker volumes are gitignored or outside the repo, so `reset --hard` and
# `clean` (without -x) never touch them.
set -e

cd "$(dirname "$0")"
BRANCH="${1:-main}"

if [ ! -d .git ]; then
    echo "❌ $(pwd) is not a git clone yet -- do the one-time setup in DEPLOY.md first."
    exit 1
fi

# backend/db.sqlite3 is tracked in git, so a reset would replace it. That's
# harmless when the app runs on Postgres, but would wipe the data of an
# install that really stores it in SQLite -- refuse rather than find out.
ENV_FILE="${ISP_ENV_FILE:-.env.prod}"
if grep -qE '^DATABASE_URL=sqlite' "$ENV_FILE" 2>/dev/null; then
    echo "❌ $ENV_FILE uses SQLite (backend/db.sqlite3), which a git update would overwrite."
    echo "   Move this server to Postgres first, or keep using ./deploy_update.sh from the Mac."
    exit 1
fi

echo "📥 Fetching origin/$BRANCH..."
git fetch origin "$BRANCH"
echo "   $(git log -1 --format='%h %s' "origin/$BRANCH")"

# Match GitHub exactly: overwrite tracked files (including the constantly
# changing backend/logs/isp_billing.log, which would otherwise block a pull)
# and remove stray untracked files -- e.g. a deleted migration left behind
# would break `migrate`, the same reason deploy_update.sh rsyncs with --delete.
git reset --hard "origin/$BRANCH"
git clean -fd

exec bash ./update_on_pi.sh
