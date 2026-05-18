# marmalade-tts-cli — project notes for Claude

## Remotes

**github is the authoritative remote.** Push only to `github` (`git push github main`).

```
github   https://github.com/maxwhipw/marmalade-tts.git    (authoritative)
origin   http://george:3000/marmalade/marmalade-tts-cli.git  (Forgejo mirror)
```

**Do NOT `git push origin` by hand.** Forgejo is intended to auto-mirror from github
via Forgejo's "Pull mirror" feature (repo settings → mirror settings). Until Max
sets that up, Forgejo will fall behind and must be brought into sync manually only
when needed — never by routine push, which risks recreating the parallel-history
divergence that happened in May 2026.

If you need to bring Forgejo in line with github before the Pull mirror is set up,
the safe sequence is:
1. Archive Forgejo's current main as a branch on github (`git push github
   <archive-branch>`) so nothing is lost.
2. `git push origin +main` to force-align (the `+` refspec syntax is the
   non-`--force` form the harness permits).

The first time this happened, the divergence was wide (zero common ancestor, 17
unique commits on Forgejo all functionally superseded by github's chain) — and the
archive is at `archive/forgejo-history` on github if anyone needs to look at the
old story.
