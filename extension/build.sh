#!/usr/bin/env bash
# Builds AdvancementsUI.jar (a Geyser extension).
# usage: ./build.sh <Geyser jar> [javac]   e.g. ./build.sh ../../../Geyser-Fabric.jar
set -euo pipefail
cd "$(dirname "$0")"
GEYSER_JAR="$(realpath "$1")"
JAVAC="${2:-javac}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
# Geyser bundles its dependencies (adventure, cumulus, ...) as nested jars.
(cd "$WORK" && unzip -q -o "$GEYSER_JAR" 'META-INF/jars/*' >/dev/null 2>&1 || true)
CP="$GEYSER_JAR"
for j in "$WORK"/META-INF/jars/*.jar; do CP="$CP:$j"; done
# Gson: present at runtime on every Geyser platform; for compiling use any copy.
GSON="$(find "${GSON_DIR:-$HOME/.m2}" "$(dirname "$GEYSER_JAR")" -name 'gson-2*.jar' 2>/dev/null | head -1 || true)"
[ -n "${GSON_JAR:-}" ] && GSON="$GSON_JAR"
CP="$CP:$GSON"
# Extra compile-only jars (checker-qual, fastutil, netty...) from LIBS_DIR if given.
if [ -n "${LIBS_DIR:-}" ]; then for j in "$LIBS_DIR"/*.jar; do CP="$CP:$j"; done; fi
mkdir -p "$WORK/classes"
"$JAVAC" --release 21 -nowarn -encoding UTF-8 -cp "$CP" -d "$WORK/classes" $(find src/main/java -name '*.java')
cp -r src/main/resources/. "$WORK/classes/"
JAR="${JAR:-$(dirname "$JAVAC")/jar}"; command -v "$JAR" >/dev/null 2>&1 || JAR=jar
mkdir -p build
(cd "$WORK/classes" && "$JAR" cf "$OLDPWD/build/AdvancementsUI.jar" .)
echo "built build/AdvancementsUI.jar"
