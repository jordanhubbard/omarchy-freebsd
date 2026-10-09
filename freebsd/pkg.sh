# Package lookups for Omarchy on FreeBSD. Sourced by the omarchy-pkg-*
# commands; translates Omarchy (Arch) package names through the pkgmap table.

OMARCHY_PKGMAP="${OMARCHY_PATH%/}/freebsd/pkgmap"

# Print the FreeBSD origin for an Omarchy package name: a category/port
# origin, @base for the base system, - when unavailable, or the name itself.
pkg_origin() {
  local origin
  origin=$(awk -v name="$1" '$1 == name && $1 !~ /^#/ { print $2; exit }' "$OMARCHY_PKGMAP" 2>/dev/null)
  printf '%s\n' "${origin:-$1}"
}

pkg_installed() {
  local origin
  origin=$(pkg_origin "$1")
  case "$origin" in
    @base) return 0 ;;
    -) return 1 ;;
    */*) pkg info -e -O "$origin" 2>/dev/null ;;
    *) pkg info -e "$origin" 2>/dev/null ;;
  esac
}

pkg_unavailable() {
  [[ $(pkg_origin "$1") == - ]]
}

pkg_as_root() {
  if ((EUID == 0)); then
    "$@"
  else
    sudo "$@"
  fi
}
