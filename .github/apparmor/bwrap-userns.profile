include <tunables/global>

profile /usr/bin/bwrap flags=(unconfined) {
    userns,
}
